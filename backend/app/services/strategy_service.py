# app/services/strategy_service.py
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.schemas import StrategyORM
from app.utils.logger import logger
from app.services.telegram import telegram_service

# --- Кэш ---
STRATEGY_CONFIG = {}
CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 минут

async def load_strategies(db: AsyncSession, use_cache: bool = True):
	"""Загрузить все стратегии из БД и собрать словарь STRATEGY_CONFIG.
		Поддержка нескольких стратегий на один символ и комбинированных индикаторов.
	"""
	global STRATEGY_CONFIG, CACHE_TIMESTAMP

	if use_cache and STRATEGY_CONFIG and (time.time() - CACHE_TIMESTAMP < CACHE_TTL):
		return STRATEGY_CONFIG

	result = await db.execute(select(StrategyORM))
	strategies = result.scalars().all()
	config = {}

	for s in strategies:
		# 🔹 Поддержка нескольких стратегий на один символ
		if s.symbol not in config:
			config[s.symbol] = []

		strategy_entry = {
			"name": s.name or f"strategy_{s.id}",
			"enabled_indicators": s.enabled_indicators or [],
			"entry_conditions": s.entry_conditions or [],

			# --- EMA / RSI / ATR ---
			"ema_short": s.ema_short or 12,
			"ema_long": s.ema_long or 26,
			"rsi_period": s.rsi_period or 14,
			"atr_period": s.atr_period or 14,

			# --- MACD ---
			"macd_fast": s.macd_fast or 12,
			"macd_slow": s.macd_slow or 26,
			"macd_signal": s.macd_signal or 9,

			# --- Stochastic ---
			"stochastic_period": s.stochastic_period or 14,

			# --- Bollinger Bands ---
			"bollinger_period": s.bollinger_period or 20,

			# --- OBV ---
			"obv_enabled": s.obv_enabled or False,

			# --- Volume SMA ---
			"volume_period": s.volume_period or 20,

			# --- VWAP ---
			"vwap_enabled": s.vwap_enabled or False,

			# --- Ichimoku Cloud ---
			"ichimoku_tenkan": s.ichimoku_tenkan or 9,
			"ichimoku_kijun": s.ichimoku_kijun or 26,
			"ichimoku_senkou": s.ichimoku_senkou or 52,

			# --- Риск-менеджмент ---
			"stop_loss": s.stop_loss or 0.02,
			"take_profit_targets": s.take_profit_targets or [0.01, 0.02],
			"take_profit_distribution": s.take_profit_distribution or [],

			"trailing_stop": bool(s.trailing_stop),
			"trailing_mode": s.trailing_mode or "none",

			# --- Управление капиталом ---
			"allocation_percent": s.allocation_percent or 1.0,
			"leverage": s.leverage or 1,

			# --- Дополнительно ---
			"enabled": s.enabled,
			"strength_multiplier": s.strength_multiplier or 1.0,
		}

		config[s.symbol].append(strategy_entry)

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

		# Обновляем глобальный конфиг
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
