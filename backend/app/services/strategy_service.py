# app/services/strategy_service.py
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.schemas import StrategyORM
from app.utils.logger import logger

# --- Кэш ---
STRATEGY_CONFIG = {}
CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 минут

async def load_strategies(db: AsyncSession, use_cache: bool = True):
	"""Загрузить все стратегии из БД и собрать словарь STRATEGY_CONFIG"""
	global STRATEGY_CONFIG, CACHE_TIMESTAMP

	# Используем кэш, если он актуален
	if use_cache and STRATEGY_CONFIG and (time.time() - CACHE_TIMESTAMP < CACHE_TTL):
		return STRATEGY_CONFIG

	result = await db.execute(select(StrategyORM))
	strategies = result.scalars().all()
	config = {}

	for s in strategies:
		config[s.symbol] = {
			"enabled_indicators": s.enabled_indicators or [],
			"entry_conditions": s.entry_conditions or [],
			"ema_short": s.ema_short or 12,
			"ema_long": s.ema_long or 26,
			"rsi_period": s.rsi_period or 14,
			"atr_period": s.atr_period or 14,
			"macd_fast": s.macd_fast or 12,
			"macd_slow": s.macd_slow or 26,
			"macd_signal": s.macd_signal or 9,
			"stochastic_period": s.stochastic_period or 14,
			"bollinger_period": s.bollinger_period or 20,
			"stop_loss": s.stop_loss or 0.02,
			"take_profit_targets": s.take_profit_targets or [0.01, 0.02],
			"take_profit_distribution": s.take_profit_distribution or [],
			"trailing_stop": s.trailing_stop or 0.0,
			"trailing_mode": s.trailing_mode or "none",
			"allocation_percent": s.allocation_percent or 1.0,
			"leverage": s.leverage or 1,
		}

	STRATEGY_CONFIG = config
	CACHE_TIMESTAMP = time.time()
	logger.info("♻️ Стратегии обновлены из БД")
	return STRATEGY_CONFIG

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

# --- Валидация ---
def validate_strategy(strategy: dict) -> bool:
	"""Проверить корректность стратегии"""
	required_fields = ["stop_loss", "take_profit_targets", "leverage"]
	for field in required_fields:
		if strategy.get(field) is None:
			logger.error(f"❌ Стратегия некорректна: отсутствует {field}")
			return False
	return True
