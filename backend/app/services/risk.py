import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.schemas import RiskLog, TradeORM
from app.utils.logger import logger
from app.services.rabbitmq import RabbitMQBroker
from app.services.strategy_service import load_strategies
from app.services.risk_service import load_risk_settings  # 🔹 новый импорт

class RiskService:
    """
    Сервис риск‑менеджмента:
    - Расчёт размера позиции (статично / динамически)
    - Проверка стоп‑лоссов, лимитов и трейлинг‑стопов
    - Унификация проверок через validate_trade()
    - Интеграция с БД и RabbitMQ (уведомления в Telegram через воркер)
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.broker = RabbitMQBroker()
        self.last_trade_time = None
        asyncio.create_task(self.broker.connect())

        # 🔹 Конфиги загружаются асинхронно через refresh_config()
        self.STRATEGY_CONFIG = {}
        self.RISK_CONFIG = {}

    async def refresh_config(self):
        """Обновить стратегии и риск‑параметры из БД"""
        try:
            self.STRATEGY_CONFIG = await load_strategies(self.db_session)
            self.RISK_CONFIG = await load_risk_settings(self.db_session)
            logger.info("♻️ RiskService configs refreshed")
        except Exception as e:
            logger.error(f"❌ Failed to refresh configs: {e}")

    async def _get_pair_performance(self, symbol: str) -> float:
        """Возвращает коэффициент производительности пары на основе winrate/прибыльности."""
        try:
            result = await self.db_session.execute(
                select(
                    func.count(TradeORM.id),
                    func.sum(TradeORM.profit_loss),
                    func.sum(func.case((TradeORM.profit_loss > 0, 1), else_=0))
                ).where(TradeORM.symbol == symbol)
            )
            total_trades, total_profit, wins = result.first()
            if not total_trades or total_trades < 30:
                return 1.0

            winrate = wins / total_trades
            avg_profit = (total_profit / total_trades) if total_trades else 0
            performance_factor = max(0.5, min(2.0, winrate * (1 + avg_profit)))
            return performance_factor
        except Exception as e:
            logger.error(f"❌ Failed to calculate performance for {symbol}: {e}")
            return 1.0

    async def calculate_position_size(
        self,
        symbol: str,
        deposit: float,
        entry_price: float,
        stop_loss_pct: float,
        strength: float = 1.0
    ) -> float:
        """Расчёт размера позиции с учётом риска, allocation и плеча."""
        risk_amount = deposit * self.RISK_CONFIG["max_risk_per_trade"]

        if self.RISK_CONFIG.get("dynamic_allocation", False):
            risk_amount *= min(strength, 2.0)

        base_allocation = self.STRATEGY_CONFIG[symbol].get("allocation_percent", 0.05)

        if self.RISK_CONFIG.get("dynamic_allocation", False):
            performance_factor = await self._get_pair_performance(symbol)
            dynamic_allocation = base_allocation * performance_factor * strength
            allocation_percent = min(dynamic_allocation, base_allocation * 2)
        else:
            allocation_percent = base_allocation

        allocated_deposit = deposit * allocation_percent
        stop_loss_amount = entry_price * stop_loss_pct
        position_size_by_risk = risk_amount / stop_loss_amount
        position_size_by_allocation = allocated_deposit / entry_price

        position_size = min(position_size_by_risk, position_size_by_allocation)
        max_position = (deposit * self.RISK_CONFIG.get("max_leverage", 1)) / entry_price
        return min(position_size, max_position)

    def calculate_leverage(self, symbol: str, strength: float) -> int:
        """Динамическое управление плечом."""
        base_leverage = self.STRATEGY_CONFIG[symbol].get("leverage", 1)
        max_leverage = self.RISK_CONFIG.get("max_leverage", base_leverage)

        if strength < 0.8:
            return 1
        elif strength < 1.5:
            return base_leverage
        else:
            return min(base_leverage + 1, max_leverage)

    def apply_stop_loss(self, entry_price: float, stop_loss_pct: float, direction: str = "long") -> float:
        if direction == "long":
            return entry_price * (1 - stop_loss_pct)
        elif direction == "short":
            return entry_price * (1 + stop_loss_pct)

    def apply_take_profit(self, entry_price: float, targets: list[float], direction: str = "long") -> list[float]:
        if direction == "long":
            return [entry_price * (1 + tp) for tp in targets]
        elif direction == "short":
            return [entry_price * (1 - tp) for tp in targets]

    def apply_trailing_stop(self, current_price: float, stop_price: float, trailing_pct: float, direction: str = "long") -> float:
        if direction == "long":
            new_stop = current_price * (1 - trailing_pct)
            return max(stop_price, new_stop)
        elif direction == "short":
            new_stop = current_price * (1 + trailing_pct)
            return min(stop_price, new_stop)

    def check_daily_loss(self, total_loss_pct: float) -> bool:
        return total_loss_pct <= self.RISK_CONFIG["max_daily_loss"]

    def check_open_trades(self, open_trades: int) -> bool:
        return open_trades < self.RISK_CONFIG["max_open_trades"]

    def check_cooldown(self) -> bool:
        cooldown = self.RISK_CONFIG.get("cooldown_between_trades", 0)
        if not self.last_trade_time:
            return True
        return datetime.utcnow() - self.last_trade_time >= timedelta(seconds=cooldown)

    async def validate_trade(
        self,
        symbol: str,
        deposit: float,
        entry_price: float,
        stop_loss_pct: float,
        open_trades: int,
        total_loss_pct: float,
        strength: float = 1.0
    ) -> bool:
        """Унифицированная проверка всех условий риска."""
        try:
            position_size = await self.calculate_position_size(symbol, deposit, entry_price, stop_loss_pct, strength)

            if not self.check_daily_loss(total_loss_pct):
                await self._log_violation("Daily loss limit exceeded")
                await self.broker.publish_telegram({"text": "❌ Daily loss limit exceeded"})
                return False

            if not self.check_open_trades(open_trades):
                await self._log_violation("Too many open trades")
                await self.broker.publish_telegram({"text": "❌ Too many open trades"})
                return False

            if not self.check_cooldown():
                await self._log_violation("Cooldown between trades not respected")
                await self.broker.publish_telegram({"text": "❌ Cooldown between trades not respected"})
                return False

            rr_ratio = self.RISK_CONFIG.get("risk_reward_ratio", 1.5)
            potential_loss = entry_price * stop_loss_pct

            tp_targets = self.STRATEGY_CONFIG[symbol].get("take_profit_targets", [0.03])
            tp_distribution = self.STRATEGY_CONFIG[symbol].get(
                "take_profit_distribution",
                [1 / len(tp_targets)] * len(tp_targets)
            )

            weighted_tp = sum(tp * w for tp, w in zip(tp_targets, tp_distribution))
            potential_profit = entry_price * weighted_tp

            if potential_profit / potential_loss < rr_ratio:
                await self._log_violation("Risk/Reward ratio too low")
                await self.broker.publish_telegram({"text": "❌ Risk/Reward ratio too low"})
                return False

            self.last_trade_time = datetime.utcnow()
            return True

        except Exception as e:
            logger.error(f"❌ Risk validation error: {e}")
            return False

    async def _log_violation(self, reason: str):
        """Сохраняет нарушение риск‑менеджмента в таблицу risk_logs."""
        try:
            log = RiskLog(reason=reason, timestamp=datetime.utcnow())
            self.db_session.add(log)
            await self.db_session.commit()
        except Exception as e:
            logger.error(f"❌ Failed to log risk violation: {e}")
            await self.db_session.rollback()

    def get_limits(self) -> dict:
        """Возвращает ключевые лимиты риск‑менеджмента для Telegram команд."""
        return {
            "stop_loss_pct": self.RISK_CONFIG.get("stop_loss_pct", "-"),
            "default_trade_loss_pct": self.RISK_CONFIG.get("default_trade_loss_pct", "-"),
            "max_trades": self.RISK_CONFIG.get("max_open_trades", "-"),
            "max_leverage": self.RISK_CONFIG.get("max_leverage", "-"),
            "max_daily_loss": self.RISK_CONFIG.get("max_daily_loss", "-"),
            "risk_reward_ratio": self.RISK_CONFIG.get("risk_reward_ratio", "-"),
            "cooldown_between_trades": self.RISK_CONFIG.get("cooldown_between_trades", "-"),
            "dynamic_allocation": self.RISK_CONFIG.get("dynamic_allocation", False)
        }
