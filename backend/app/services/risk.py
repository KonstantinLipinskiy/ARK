import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import STRATEGY_CONFIG, RISK_CONFIG
from app.db.schemas import RiskLog
from app.utils.logger import logger
from app.services.telegram import TelegramService

class RiskService:
	"""
	Сервис риск‑менеджмента:
	- Расчёт размера позиции
	- Проверка стоп‑лоссов, лимитов и трейлинг‑стопов
	- Унификация проверок через validate_trade()
	- Интеграция с БД и Telegram
	"""

	def __init__(self, db_session: AsyncSession, telegram: TelegramService):
		self.db_session = db_session
		self.telegram = telegram
		self.last_trade_time = None

	async def calculate_position_size(
			self,
			symbol: str,
			deposit: float,
			entry_price: float,
			stop_loss_pct: float,
			strength: float = 1.0
		) -> float:
		"""
		Расчёт размера позиции с учётом:
		- риска (max_risk_per_trade),
		- allocation_percent для пары,
		- динамического распределения (strength),
		- максимального плеча.
		"""

		# 1. Базовый риск
		risk_amount = deposit * RISK_CONFIG["max_risk_per_trade"]

		if RISK_CONFIG.get("DYNAMIC_ALLOCATION", False):
			# динамическое распределение риска: сильный сигнал → больше риск
			risk_amount *= min(strength, 2.0)  # ограничиваем коэффициент

		# 2. Ограничение по проценту депозита для пары
		allocation_percent = STRATEGY_CONFIG[symbol].get("allocation_percent", 0.05)
		allocated_deposit = deposit * allocation_percent

		# 3. Потеря на 1 монету при стопе
		stop_loss_amount = entry_price * stop_loss_pct

		# 4. Размер позиции по риску
		position_size_by_risk = risk_amount / stop_loss_amount

		# 5. Размер позиции по allocation_percent
		position_size_by_allocation = allocated_deposit / entry_price

		# 6. Итоговый размер позиции = минимум из двух
		position_size = min(position_size_by_risk, position_size_by_allocation)

		# 7. Ограничение плечом
		max_position = (deposit * RISK_CONFIG.get("max_leverage", 1)) / entry_price
		return min(position_size, max_position)

	# Уровень stop_loss
	def apply_stop_loss(self, entry_price: float, stop_loss_pct: float) -> float:
		return entry_price * (1 - stop_loss_pct)

	# функция считает уровни тейк‑профита
	def apply_take_profit(self, entry_price: float, targets: list[float]) -> list[float]:
		return [entry_price * (1 + tp) for tp in targets]

	# стоп двигается за ценой
	def apply_trailing_stop(self, current_price: float, stop_price: float, trailing_pct: float) -> float:
		new_stop = current_price * (1 - trailing_pct)
		return max(stop_price, new_stop)

	# превышение дневного лимита убытков
	def check_daily_loss(self, total_loss_pct: float) -> bool:
		return total_loss_pct <= RISK_CONFIG["max_daily_loss"]

	# проверка количества одновременно открытых сделок
	def check_open_trades(self, open_trades: int) -> bool:
		return open_trades < RISK_CONFIG["max_open_trades"]

	def check_cooldown(self) -> bool:
		"""
		Проверка задержки между сделками.
		"""
		cooldown = RISK_CONFIG.get("cooldown_between_trades", 0)
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
		"""
		Унифицированная проверка всех условий риска.
		"""
		try:
			# размер позиции
			position_size = await self.calculate_position_size(symbol, deposit, entry_price, stop_loss_pct, strength)

			if not self.check_daily_loss(total_loss_pct):
					await self._log_violation("Daily loss limit exceeded")
					await self.telegram.send_message("❌ Daily loss limit exceeded")
					return False

			if not self.check_open_trades(open_trades):
					await self._log_violation("Too many open trades")
					await self.telegram.send_message("❌ Too many open trades")
					return False

			if not self.check_cooldown():
					await self._log_violation("Cooldown between trades not respected")
					await self.telegram.send_message("❌ Cooldown between trades not respected")
					return False

			# риск‑ревард проверка (многоуровневые TP)
			rr_ratio = RISK_CONFIG.get("risk_reward_ratio", 1.5)
			potential_loss = entry_price * stop_loss_pct

			tp_targets = STRATEGY_CONFIG[symbol].get("take_profit_targets", [0.03])
			# считаем средневзвешенный TP (равномерно, если веса не заданы)
			avg_tp = sum(tp_targets) / len(tp_targets)
			potential_profit = entry_price * avg_tp

			if potential_profit / potential_loss < rr_ratio:
					await self._log_violation("Risk/Reward ratio too low")
					await self.telegram.send_message("❌ Risk/Reward ratio too low")
					return False

			self.last_trade_time = datetime.utcnow()
			return True

		except Exception as e:
			logger.error(f"❌ Risk validation error: {e}")
			return False

	async def _log_violation(self, reason: str):
		"""
		Сохраняет нарушение риск‑менеджмента в таблицу risk_logs.
		"""
		try:
			log = RiskLog(reason=reason, timestamp=datetime.utcnow())
			self.db_session.add(log)
			await self.db_session.commit()
		except Exception as e:
			logger.error(f"❌ Failed to log risk violation: {e}")
			await self.db_session.rollback()
