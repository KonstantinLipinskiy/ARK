# app/services/risk_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.schemas import RiskSettingsORM
from app.utils.logger import logger

async def load_risk_settings(db: AsyncSession) -> dict:
	"""Загрузить текущие параметры риска из БД"""
	result = await db.execute(select(RiskSettingsORM).limit(1))
	settings = result.scalar_one_or_none()

	if not settings:
		logger.warning("⚠️ В таблице risk_settings нет записей, используются дефолтные значения")
		return {
			"max_risk_per_trade": 0.01,
			"max_open_trades": 5,
			"max_daily_loss": 0.05,
			"max_leverage": 3,
			"cooldown_between_trades": 60,
			"risk_reward_ratio": 1.5,
			"dynamic_allocation": False,
		}

	return {
		"max_risk_per_trade": settings.max_risk_per_trade,
		"max_open_trades": settings.max_open_trades,
		"max_daily_loss": settings.max_daily_loss,
		"max_leverage": settings.max_leverage,
		"cooldown_between_trades": settings.cooldown_between_trades,
		"risk_reward_ratio": settings.risk_reward_ratio,
		"dynamic_allocation": settings.dynamic_allocation,
	}

async def update_risk_settings(db: AsyncSession, updates: dict) -> dict | None:
	"""Обновить параметры риска"""
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

		return await load_risk_settings(db)
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка обновления risk_settings: {e}")
		await db.rollback()
		return None
