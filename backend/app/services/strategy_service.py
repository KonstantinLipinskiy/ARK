from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.schemas import StrategyORM
from app.utils.logger import logger
from app.services.telegram import telegram_service
from app.services.exchange import load_strategies   # ✅ теперь импортируем из exchange.py

# --- CRUD операции ---
async def add_strategy(db: AsyncSession, strategy_data: dict):
	"""Добавить новую стратегию"""
	try:
		if not validate_strategy(strategy_data):
			return None
		strategy = StrategyORM(**strategy_data)
		db.add(strategy)
		await db.commit()
		await db.refresh(strategy)
		logger.info(f"✅ Стратегия {strategy.symbol} добавлена")
		await telegram_service.send_strategy_updated(strategy_data)
		return strategy
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка добавления стратегии: {e}")
		await db.rollback()
		return None

async def update_strategy(db: AsyncSession, symbol: str, updates: dict):
	"""Обновить стратегию по символу"""
	try:
		result = await db.execute(select(StrategyORM).where(StrategyORM.symbol == symbol))
		strategy = result.scalar_one_or_none()
		if not strategy:
			logger.warning(f"⚠️ Стратегия {symbol} не найдена для обновления")
			return None

		for key, value in updates.items():
			if hasattr(strategy, key):
					setattr(strategy, key, value)

		await db.commit()
		await db.refresh(strategy)
		logger.info(f"♻️ Стратегия {symbol} обновлена")
		await telegram_service.send_strategy_updated(updates)
		return strategy
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка обновления стратегии: {e}")
		await db.rollback()
		return None

async def delete_strategy(db: AsyncSession, symbol: str):
	"""Удалить стратегию по символу"""
	try:
		result = await db.execute(select(StrategyORM).where(StrategyORM.symbol == symbol))
		strategy = result.scalar_one_or_none()
		if not strategy:
			logger.warning(f"⚠️ Стратегия {symbol} не найдена для удаления")
			return False

		await db.delete(strategy)
		await db.commit()
		logger.info(f"🗑️ Стратегия {symbol} удалена")
		return True
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка удаления стратегии: {e}")
		await db.rollback()
		return False

# --- Toggle ---
async def toggle_strategy(db: AsyncSession, symbol: str, enabled: bool):
	"""Включить/выключить стратегию и синхронизировать конфиг с ботом"""
	try:
		result = await db.execute(select(StrategyORM).where(StrategyORM.symbol == symbol))
		strategy = result.scalar_one_or_none()
		if not strategy:
			logger.warning(f"⚠️ Стратегия {symbol} не найдена для переключения")
			return None

		strategy.enabled = enabled
		await db.commit()
		await db.refresh(strategy)

		# ✅ обновляем глобальный конфиг через exchange.py
		await load_strategies(db, use_cache=False)

		status = "включена" if enabled else "выключена"
		logger.info(f"🔀 Стратегия {symbol} {status}")
		await telegram_service.send_strategy_updated({"symbol": symbol, "enabled": enabled})
		return strategy
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка переключения стратегии {symbol}: {e}")
		await db.rollback()
		return None

# --- Валидация ---
def validate_strategy(strategy: dict) -> bool:
	"""Проверить корректность стратегии"""
	required_fields = ["stop_loss", "take_profit_targets", "leverage"]
	for field in required_fields:
		if strategy.get(field) is None:
			logger.error(f"❌ Стратегия некорректна: отсутствует {field}")
			return False
	return True
