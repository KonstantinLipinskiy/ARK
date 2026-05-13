import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.schemas import RiskLog, TradeORM, UserORM
from app.utils.logger import logger
from app.services.rabbitmq import RabbitMQBroker
from app.services.strategy_service import load_strategies
from app.services.risk_service import load_risk_settings

# 🔹 Профили риска
RISK_PROFILES = {
    "conservative": {"max_risk_per_trade": 0.005, "max_daily_loss": 0.03, "max_leverage": 1},
    "moderate": {"max_risk_per_trade": 0.01, "max_daily_loss": 0.05, "max_leverage": 3},
    "aggressive": {"max_risk_per_trade": 0.02, "max_daily_loss": 0.1, "max_leverage": 5},
}

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
		self._user_risk_cache = {}  # 🔹 кэш для user_id → risk_config

	async def refresh_config(self):
		"""Обновить стратегии и риск‑параметры из БД"""
		try:
			self.STRATEGY_CONFIG = await load_strategies(self.db_session)
			self.RISK_CONFIG = await load_risk_settings(self.db_session)
			self._user_risk_cache.clear()
			logger.info("♻️ RiskService configs refreshed")
		except Exception as e:
			logger.error(f"❌ Failed to refresh configs: {e}")

	async def get_user_risk_config(self, user_id: int) -> dict:
		"""Возвращает индивидуальные параметры риска пользователя (с кэшированием)."""
		if user_id in self._user_risk_cache:
			return self._user_risk_cache[user_id]

		try:
			result = await self.db_session.execute(select(UserORM).filter(UserORM.id == user_id))
			user = result.scalars().first()
			if not user or not user.settings:
					self._user_risk_cache[user_id] = self.RISK_CONFIG
					return self.RISK_CONFIG

			profile = user.settings.get("risk_profile", None)
			custom_config = user.settings.get("custom_risk", {})

			if profile and profile in RISK_PROFILES:
					config = {**self.RISK_CONFIG, **RISK_PROFILES[profile], **custom_config}
			else:
					config = {**self.RISK_CONFIG, **custom_config}

			self._user_risk_cache[user_id] = config
			return config
		except Exception as e:
			logger.error(f"❌ Failed to load user risk profile: {e}")
			return self.RISK_CONFIG

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
		strength: float = 1.0,
		user_id: int | None = None,
		ml_confidence: float | None = None
	) -> float:
		"""Расчёт размера позиции с учётом риска, allocation, силы сигнала и ML confidence."""
		risk_config = await self.get_user_risk_config(user_id) if user_id else self.RISK_CONFIG
		risk_amount = deposit * risk_config["max_risk_per_trade"]

		# --- масштабирование риска ---
		if risk_config.get("dynamic_allocation", False):
			multiplier = min(strength, 2.0)
			if ml_confidence:
				multiplier *= (1 + ml_confidence)
			risk_amount *= multiplier

		# --- базовые параметры стратегии ---
		base_allocation = self.STRATEGY_CONFIG[symbol].get("allocation_percent", 0.05)
		strength_multiplier = self.STRATEGY_CONFIG[symbol].get("strength_multiplier", 1.0)

		# --- динамическая аллокация ---
		if risk_config.get("dynamic_allocation", False):
			performance_factor = await self._get_pair_performance(symbol)
			confidence_factor = 1.0 + (ml_confidence or 0)  # учёт доверия ML
			dynamic_allocation = (
				base_allocation
				* performance_factor
				* strength
				* strength_multiplier
				* confidence_factor
			)
			allocation_percent = min(dynamic_allocation, base_allocation * 2)
		else:
			allocation_percent = base_allocation

		# --- итоговый размер позиции ---
		allocated_deposit = deposit * allocation_percent
		stop_loss_amount = entry_price * stop_loss_pct
		position_size_by_risk = risk_amount / stop_loss_amount
		position_size_by_allocation = allocated_deposit / entry_price

		position_size = min(position_size_by_risk, position_size_by_allocation)
		max_position = (deposit * risk_config.get("max_leverage", 1)) / entry_price
		return min(position_size, max_position)


	def calculate_leverage(self, symbol: str, strength: float, user_risk_config: dict | None = None) -> int:
		"""Динамическое управление плечом."""
		risk_config = user_risk_config or self.RISK_CONFIG
		base_leverage = self.STRATEGY_CONFIG[symbol].get("leverage", 1)
		max_leverage = risk_config.get("max_leverage", base_leverage)

		if strength < 0.8:
			return 1
		elif strength < 1.5:
			return base_leverage
		else:
			return min(base_leverage + 1, max_leverage)

	def apply_stop_loss(self, entry_price: float, stop_loss_pct: float, direction: str = "long") -> float:
		return entry_price * (1 - stop_loss_pct) if direction == "long" else entry_price * (1 + stop_loss_pct)

	def apply_take_profit(self, entry_price: float, targets: list[float], direction: str = "long") -> list[float]:
		return [entry_price * (1 + tp) for tp in targets] if direction == "long" else [entry_price * (1 - tp) for tp in targets]

	def apply_trailing_stop(self, current_price: float, stop_price: float, trailing_pct: float, direction: str = "long") -> float:
		if direction == "long":
			new_stop = current_price * (1 - trailing_pct)
			return max(stop_price, new_stop)
		else:
			new_stop = current_price * (1 + trailing_pct)
			return min(stop_price, new_stop)

	def check_daily_loss(self, total_loss_pct: float, risk_config: dict) -> bool:
		return total_loss_pct <= risk_config["max_daily_loss"]

	def check_open_trades(self, open_trades: int, risk_config: dict) -> bool:
		return open_trades < risk_config["max_open_trades"]

	def check_cooldown(self, risk_config: dict) -> bool:
		cooldown = risk_config.get("cooldown_between_trades", 0)
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
		strength: float = 1.0,
		user_id: int | None = None
	) -> bool:
		"""Унифицированная проверка всех условий риска."""
		try:
			risk_config = await self.get_user_risk_config(user_id) if user_id else self.RISK_CONFIG
			position_size = await self.calculate_position_size(
					symbol, deposit, entry_price, stop_loss_pct, strength, user_id
			)

			# --- Проверка дневного лимита ---
			if not self.check_daily_loss(total_loss_pct, risk_config):
					await self._log_violation("Daily loss limit exceeded", symbol, position_size, deposit)
					await self.broker.publish_telegram({
						"type": "risk_violation",
						"user_id": user_id,
						"reason": "Daily loss limit exceeded",
						"symbol": symbol,
						"position_size": position_size,
						"deposit": deposit
					})
					return False

			# --- Проверка количества сделок ---
			if not self.check_open_trades(open_trades, risk_config):
					await self._log_violation("Too many open trades", symbol, position_size, deposit)
					await self.broker.publish_telegram({
						"type": "risk_violation",
						"user_id": user_id,
						"reason": "Too many open trades",
						"symbol": symbol,
						"position_size": position_size,
						"deposit": deposit
					})
					return False

			# --- Проверка cooldown ---
			if not self.check_cooldown(risk_config):
					await self._log_violation("Cooldown between trades not respected", symbol, position_size, deposit)
					await self.broker.publish_telegram({
						"type": "risk_violation",
						"user_id": user_id,
						"reason": "Cooldown not respected",
						"symbol": symbol,
						"position_size": position_size,
						"deposit": deposit
					})
					return False

			# --- Проверка Risk/Reward ---
			rr_ratio = risk_config.get("risk_reward_ratio", 1.5)
			potential_loss = entry_price * stop_loss_pct

			tp_targets = self.STRATEGY_CONFIG[symbol].get("take_profit_targets", [0.03])
			tp_distribution = self.STRATEGY_CONFIG[symbol].get(
					"take_profit_distribution",
					[1 / len(tp_targets)] * len(tp_targets)
			)

			weighted_tp = sum(tp * w for tp, w in zip(tp_targets, tp_distribution))
			potential_profit = entry_price * weighted_tp

			if potential_profit / potential_loss < rr_ratio:
					await self._log_violation("Risk/Reward ratio too low", symbol, position_size, deposit)
					await self.broker.publish_telegram({
						"type": "risk_violation",
						"user_id": user_id,
						"reason": "Risk/Reward ratio too low",
						"symbol": symbol,
						"position_size": position_size,
						"deposit": deposit
					})
					return False

			# --- Успешная валидация ---
			self.last_trade_time = datetime.utcnow()
			await self.broker.publish_telegram({
					"type": "trade",
					"user_id": user_id,
					"trade": {
						"pair": symbol,
						"status": "validated",
						"entry": entry_price,
						"stop_loss": stop_loss_pct,
						"take_profit": tp_targets,
						"leverage": risk_config.get("max_leverage", 1),
						"confidence_score": strength
					}
			})
			return True

		except Exception as e:
			logger.error(f"❌ Risk validation error: {e}")
			await self.broker.publish_telegram({
					"type": "error",
					"user_id": user_id,
					"error": f"Risk validation error: {e}"
			})
			return False

