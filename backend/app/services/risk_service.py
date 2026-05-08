# app/services/risk_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.db.schemas import RiskSettingsORM, RiskSettingsLogORM
from app.utils.logger import logger

# 🔹 Кэш для настроек риска
_risk_cache: dict | None = None

async def load_risk_settings(db: AsyncSession, use_cache: bool = True) -> dict:
	"""Загрузить текущие параметры риска из БД (с кэшированием)."""
	global _risk_cache
	if use_cache and _risk_cache:
		return _risk_cache

	result = await db.execute(select(RiskSettingsORM).limit(1))
	settings = result.scalar_one_or_none()

	if not settings:
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
		"max_risk_per_trade": settings.max_risk_per_trade,
		"max_open_trades": settings.max_open_trades,
		"max_daily_loss": settings.max_daily_loss,
		"max_leverage": settings.max_leverage,
		"cooldown_between_trades": settings.cooldown_between_trades,
		"risk_reward_ratio": settings.risk_reward_ratio,
		"dynamic_allocation": settings.dynamic_allocation,
	}
	return _risk_cache

async def update_risk_settings(db: AsyncSession, updates: dict, updated_by: str = "system") -> dict | None:
	"""Обновить параметры риска и сохранить историю изменений."""
	global _risk_cache
	try:
		result = await db.execute(select(RiskSettingsORM).limit(1))
		settings = result.scalar_one_or_none()

		if not settings:
			# если записи нет — создаём новую
			settings = RiskSettingsORM(**updates)
			db.add(settings)
		else:
			for key, value in updates.items():
					if hasattr(settings, key):
						setattr(settings, key, value)

		await db.commit()
		await db.refresh(settings)
		logger.info("♻️ Параметры риска обновлены")

		# 🔹 Логируем изменения
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

		# 🔹 Обновляем кэш
		_risk_cache = await load_risk_settings(db, use_cache=False)
		return _risk_cache

	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка обновления risk_settings: {e}")
		await db.rollback()
		return None
