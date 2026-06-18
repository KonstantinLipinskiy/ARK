# app/services/risk_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.db.schemas import RiskSettingsORM, RiskSettingsLogORM
from app.utils.logger import logger
from app.config import settings

# 🔹 Кэш для настроек риска
_risk_cache: dict | None = None

async def load_risk_settings(db: AsyncSession, use_cache: bool = True) -> dict:
	"""Загрузить текущие параметры риска из БД (с кэшированием)."""
	global _risk_cache
	if use_cache and _risk_cache:
		return _risk_cache

	result = await db.execute(select(RiskSettingsORM).limit(1))
	risk_settings = result.scalar_one_or_none()

	if not risk_settings:
		logger.warning("⚠️ В таблице risk_settings нет записей, используются дефолтные значения")
		_risk_cache = {
			"max_risk_per_trade": 0.01,
			"max_open_trades": 5,
			"max_daily_loss": 0.05,
			"max_leverage": 3,
			"cooldown_between_trades": 60,
			"risk_reward_ratio": 1.5,
			"dynamic_allocation": False,
		}
		return _risk_cache

	_risk_cache = {
		"max_risk_per_trade": risk_settings.max_risk_per_trade,
		"max_open_trades": risk_settings.max_open_trades,
		"max_daily_loss": risk_settings.max_daily_loss,
		"max_leverage": risk_settings.max_leverage,
		"cooldown_between_trades": risk_settings.cooldown_between_trades,
		"risk_reward_ratio": risk_settings.risk_reward_ratio,
		"dynamic_allocation": risk_settings.dynamic_allocation,
	}
	return _risk_cache

async def update_risk_settings(db: AsyncSession, updates: dict, updated_by: str = "system") -> dict | None:
	"""Обновить параметры риска и сохранить историю изменений."""
	global _risk_cache
	try:
		result = await db.execute(select(RiskSettingsORM).limit(1))
		risk_settings = result.scalar_one_or_none()

		if not risk_settings:
			risk_settings = RiskSettingsORM(**updates)
			db.add(risk_settings)
		else:
			for key, value in updates.items():
				if hasattr(risk_settings, key):
					setattr(risk_settings, key, value)

		await db.commit()
		await db.refresh(risk_settings)
		logger.info("♻️ Параметры риска обновлены")

		try:
			log_entry = RiskSettingsLogORM(
				updated_by=updated_by,
				updates=str(updates),
				timestamp=datetime.utcnow()
			)
			db.add(log_entry)
			await db.commit()
		except Exception as log_err:
			logger.error(f"⚠️ Ошибка логирования изменений risk_settings: {log_err}")
			await db.rollback()

		_risk_cache = await load_risk_settings(db, use_cache=False)
		return _risk_cache

	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка обновления risk_settings: {e}")
		await db.rollback()
		return None

# --- Расчёт размера позиции ---
async def calculate_position_size(symbol: str, deposit: float, entry_price: float,
									stop_loss_pct: float, strength: float, ml_confidence: float) -> float:
	"""
	Рассчитать размер позиции на основе депозита, стоп-лосса, силы сигнала и confidence.
	"""
	risk_settings = _risk_cache or {}
	max_risk_per_trade = risk_settings.get("max_risk_per_trade", 0.01)

	# Потенциальный риск = депозит * max_risk_per_trade
	risk_capital = deposit * max_risk_per_trade

	# Размер позиции = риск / (entry_price * stop_loss_pct)
	position_size = risk_capital / (entry_price * stop_loss_pct)

	# Корректировка по силе сигнала и confidence
	adjusted_size = position_size * (settings.AMOUNT_FACTOR + ml_confidence) * strength

	return max(adjusted_size, 0.0)

# --- Валидация сделки ---
async def validate_trade(symbol: str, deposit: float, entry_price: float,
							stop_loss_pct: float, open_trades: int,
							total_loss_pct: float, strength: float) -> bool:
	"""
	Проверить сделку на соответствие лимитам риска.
	"""
	risk_settings = _risk_cache or {}
	max_open_trades = risk_settings.get("max_open_trades", 5)
	max_daily_loss = risk_settings.get("max_daily_loss", 0.05)

	# Проверка количества открытых сделок
	if open_trades >= max_open_trades:
		logger.warning(f"⚠️ Превышен лимит открытых сделок ({open_trades}/{max_open_trades})")
		return False

	# Проверка дневного убытка
	if total_loss_pct > max_daily_loss:
		logger.warning(f"⚠️ Превышен дневной лимит убытка ({total_loss_pct}/{max_daily_loss})")
		return False

	# Проверка силы сигнала
	if strength < settings.CONFIDENCE_THRESHOLD:
		logger.warning(f"⚠️ Сигнал отклонён: strength={strength:.2f} < threshold={settings.CONFIDENCE_THRESHOLD}")
		return False

	return True

# --- Универсальная валидация сигнала ---
def validate_signal(signal: dict) -> tuple[bool, str]:
	"""
	Проверка торгового сигнала на соответствие бизнес-правилам.
	Возвращает (is_valid, message).
	"""
	action = signal.get("action", "").lower()
	strength = signal.get("strength", 0.0)
	test_flag = signal.get("test", False)

	if action not in ["buy", "sell"]:
		return False, "⚠️ Сигнал проигнорирован (неключевой)"
	if strength < settings.MIN_SIGNAL_STRENGTH:
		return False, f"⚠️ Сигнал проигнорирован (слабый strength={strength:.2f})"
	if test_flag and not settings.ALLOW_TEST_SIGNALS:
		return False, "⚠️ Сигнал проигнорирован (тестовый)"

	return True, "✅ Ключевой сигнал принят"
