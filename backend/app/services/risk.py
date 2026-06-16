#app/services/risk.py
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.schemas import RiskLog, TradeORM, UserORM, FundingRateORM
from app.utils.logger import logger
from app.broker.rabbitmq import RabbitMQBroker
from app.services.exchange import load_strategies, get_funding_rate, get_mark_price
from app.services.risk_service import load_risk_settings
from app.config import settings

RISK_PROFILES = {
	"conservative": {"max_risk_per_trade": 0.005, "max_daily_loss": 0.03, "max_leverage": 1},
	"moderate": {"max_risk_per_trade": 0.01, "max_daily_loss": 0.05, "max_leverage": 3},
	"aggressive": {"max_risk_per_trade": 0.02, "max_daily_loss": 0.1, "max_leverage": 5},
}

class RiskService:
	def __init__(self, db_session: AsyncSession):
		self.db_session = db_session
		self.broker = RabbitMQBroker()
		self.last_trade_time = None
		asyncio.create_task(self.broker.connect())

		self.STRATEGY_CONFIG = {}
		self.RISK_CONFIG = {}
		self._user_risk_cache = {}

		asyncio.create_task(self.refresh_config())

	async def refresh_config(self):
		"""Обновить стратегии и риск‑параметры из БД"""
		try:
			self.STRATEGY_CONFIG = await load_strategies(self.db_session)
			self.RISK_CONFIG = await load_risk_settings(self.db_session)
			self._user_risk_cache.clear()
			logger.info("♻️ RiskService configs refreshed")
		except Exception as e:
			logger.error(f"❌ Failed to refresh configs: {e}")

	# --- FUNDING RATE ---
	async def save_funding_rate(self, symbol: str):
		"""Получить и сохранить ставку финансирования в БД."""
		try:
			funding = await get_funding_rate(symbol)
			if "error" in funding:
				return funding

			record = FundingRateORM(
				symbol=symbol,
				rate=funding["fundingRate"],
				timestamp=funding["timestamp"]
			)
			self.db_session.add(record)
			await self.db_session.commit()
			logger.info(f"✅ Funding rate saved for {symbol}: {funding['fundingRate']}")
			return record
		except Exception as e:
			logger.error(f"❌ Failed to save funding rate for {symbol}: {e}")
			return {"error": str(e)}

	# --- LIQUIDATION RISK ---
	async def check_liquidation_risk(self, symbol: str, entry_price: float, leverage: int) -> bool:
		"""Проверка приближения к ликвидации через mark price."""
		try:
			mark = await get_mark_price(symbol)
			if "error" in mark:
				return False

			mark_price = mark["markPrice"]
			liquidation_threshold = entry_price * (1 - 1 / leverage)
			if mark_price <= liquidation_threshold:
				logger.warning(f"⚠️ {symbol} близко к ликвидации! Mark={mark_price}, Entry={entry_price}")
				return True
			return False
		except Exception as e:
			logger.error(f"❌ Liquidation risk check failed for {symbol}: {e}")
			return False

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
		deposit: float | None,
		entry_price: float,
		stop_loss_pct: float,
		strength: float = 1.0,
		user_id: int | None = None,
		ml_confidence: float | None = None
	) -> float:
		"""Расчёт размера позиции с учётом риска, allocation, силы сигнала и ML confidence."""
		risk_config = await self.get_user_risk_config(user_id) if user_id else self.RISK_CONFIG

		# --- депозит из настроек ---
		deposit = deposit or risk_config.get("default_deposit", settings.DEFAULT_DEPOSIT)

		# --- комиссия и проскальзывание ---
		commission = risk_config.get("commission_rate", settings.COMMISSION_RATE)
		slippage = risk_config.get("slippage_tolerance", settings.SLIPPAGE_TOLERANCE)
		effective_entry = entry_price * (1 + commission + slippage)

		risk_amount = deposit * risk_config.get("max_risk_per_trade", 0.01)

		# --- масштабирование риска ---
		if risk_config.get("dynamic_allocation", False):
			multiplier = min(strength * risk_config.get("signal_strength_multiplier", settings.SIGNAL_STRENGTH_MULTIPLIER), 3.0)
			if ml_confidence:
				multiplier *= (1 + ml_confidence)
			risk_amount *= multiplier

		# --- базовые параметры стратегии ---
		if symbol not in self.STRATEGY_CONFIG:
			await self.refresh_config()
			if symbol not in self.STRATEGY_CONFIG:
				logger.error(f"❌ Strategy config not found for {symbol}")
				return 0.0

		base_allocation = self.STRATEGY_CONFIG[symbol].get("allocation_percent", 0.05)
		strength_multiplier = self.STRATEGY_CONFIG[symbol].get("strength_multiplier", 1.0)

		# --- динамическая аллокация ---
		if risk_config.get("dynamic_allocation", False):
			performance_factor = await self._get_pair_performance(symbol)
			confidence_factor = 1.0 + (ml_confidence or 0)
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
		stop_loss_amount = effective_entry * stop_loss_pct
		position_size_by_risk = risk_amount / stop_loss_amount if stop_loss_amount > 0 else 0
		position_size_by_allocation = allocated_deposit / effective_entry if effective_entry > 0 else 0

		position_size = min(position_size_by_risk, position_size_by_allocation)
		max_position = (deposit * risk_config.get("max_leverage", 1)) / effective_entry if effective_entry > 0 else 0
		return min(position_size, max_position)

	def calculate_leverage(self, symbol: str, strength: float, user_risk_config: dict | None = None) -> int:
		"""Динамическое управление плечом."""
		risk_config = user_risk_config or self.RISK_CONFIG
		base_leverage = self.STRATEGY_CONFIG.get(symbol, {}).get("leverage", 1)
		max_leverage = risk_config.get("max_leverage", base_leverage)

		if strength < 0.8:
			return 1
		elif strength < 1.5:
			return base_leverage
		else:
			return min(base_leverage + 1, max_leverage)

	def apply_stop_loss(
		self,
		entry_price: float,
		stop_loss_pct: float,
		direction: str = "long",
		atr: float | None = None,
		risk_config: dict | None = None
	) -> float:
		"""Расчёт стоп-лосса с учётом ATR множителя."""
		atr_mult = (risk_config or self.RISK_CONFIG).get("atr_multiplier", settings.ATR_MULTIPLIER)
		if direction == "long":
			stop = entry_price * (1 - stop_loss_pct)
			if atr:
				stop = min(stop, entry_price - atr_mult * atr)
		else:
			stop = entry_price * (1 + stop_loss_pct)
			if atr:
				stop = max(stop, entry_price + atr_mult * atr)
		return stop

	def apply_take_profit(
		self,
		entry_price: float,
		targets: list[float],
		direction: str = "long",
		risk_config: dict | None = None
	) -> list[float]:
		"""Расчёт тейк-профитов с учётом комиссии и проскальзывания."""
		commission = (risk_config or self.RISK_CONFIG).get("commission_rate", settings.COMMISSION_RATE)
		slippage = (risk_config or self.RISK_CONFIG).get("slippage_tolerance", settings.SLIPPAGE_TOLERANCE)
		effective_entry = entry_price * (1 + commission + slippage)

		if direction == "long":
			return [effective_entry * (1 + tp) for tp in targets]
		else:
			return [effective_entry * (1 - tp) for tp in targets]

	def apply_trailing_stop(self, current_price: float, stop_price: float, trailing_pct: float, direction: str = "long") -> float:
		if direction == "long":
			new_stop = current_price * (1 - trailing_pct)
			return max(stop_price, new_stop)
		else:
			new_stop = current_price * (1 + trailing_pct)
			return min(stop_price, new_stop)

	def check_daily_loss(self, total_loss_pct: float, risk_config: dict) -> bool:
		return total_loss_pct <= risk_config.get("max_daily_loss", 0.05)

	def check_open_trades(self, open_trades: int, risk_config: dict) -> bool:
		return open_trades < risk_config.get("max_open_trades", 5)

	def check_cooldown(self, risk_config: dict) -> bool:
		cooldown = risk_config.get("cooldown_between_trades", 0)
		if not self.last_trade_time:
			return True
		return datetime.utcnow() - self.last_trade_time >= timedelta(seconds=cooldown)

	async def _log_violation(self, reason: str, symbol: str, position_size: float, deposit: float):
		"""Запись нарушения риск-менеджмента в БД и лог."""
		try:
			violation = RiskLog(
				reason=reason,
				symbol=symbol,
				position_size=position_size,
				deposit=deposit,
				timestamp=datetime.utcnow()
			)
			self.db_session.add(violation)
			await self.db_session.commit()
			logger.warning(f"⚠️ Risk violation: {reason} | {symbol} | pos={position_size:.4f} | dep={deposit}")
		except Exception as e:
			logger.error(f"❌ Failed to log violation: {e}")

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
		"""Унифицированная проверка всех условий риска и стратегии."""
		try:
			# ✅ проверка, что конфиги загружены
			if not self.STRATEGY_CONFIG or not self.RISK_CONFIG:
				await self.refresh_config()

			if symbol not in self.STRATEGY_CONFIG:
				logger.error(f"❌ Strategy config not found for {symbol}")
				return False

			strategy = self.STRATEGY_CONFIG[symbol]
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

			# --- Проверка условий стратегии ---
			direction = None

			# RSI thresholds
			last_rsi = strategy.get("last_rsi")
			rsi_lower = strategy.get("rsi_lower_threshold", 30)
			rsi_upper = strategy.get("rsi_upper_threshold", 70)
			if last_rsi is not None:
				if last_rsi < rsi_lower:
					direction = "long"
				elif last_rsi > rsi_upper:
					direction = "short"

			# Stochastic thresholds
			last_stoch = strategy.get("last_stoch")
			stoch_lower = strategy.get("stochastic_lower_threshold", 20)
			stoch_upper = strategy.get("stochastic_upper_threshold", 80)
			if last_stoch is not None:
				if last_stoch < stoch_lower:
					direction = "long"
				elif last_stoch > stoch_upper:
					direction = "short"

			# Sentiment thresholds
			last_sentiment = strategy.get("last_sentiment")
			sentiment_long = strategy.get("sentiment_long_threshold", -0.5)
			sentiment_short = strategy.get("sentiment_short_threshold", 0.5)
			if direction == "long" and last_sentiment is not None and last_sentiment < sentiment_long:
				await self._log_violation("Sentiment blocks long entry", symbol, position_size, deposit)
				return False
			if direction == "short" and last_sentiment is not None and last_sentiment > sentiment_short:
				await self._log_violation("Sentiment blocks short entry", symbol, position_size, deposit)
				return False

			# --- Проверка Risk/Reward ---
			rr_ratio = risk_config.get("risk_reward_ratio", 1.5)
			potential_loss = entry_price * stop_loss_pct

			tp_targets = strategy.get("take_profit_targets", [0.03])
			tp_distribution = strategy.get(
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

