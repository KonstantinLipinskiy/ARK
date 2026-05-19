import ccxt.async_support as ccxt
from sqlalchemy import select
import asyncio
import time
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.config import settings
from app.utils.logger import logger
from app.services.risk import RiskService
from app.services.telegram import TelegramService
from app.db.schemas import TradeORM, StrategyORM, OHLCVHourly


# --- INIT ---
def get_exchange():
	"""
	Инициализация клиента биржи через ccxt.
	"""
	exchange_class = getattr(ccxt, settings.EXCHANGE_CONFIG["name"])
	exchange = exchange_class({
		"apiKey": settings.EXCHANGE_CONFIG["api_key"],
		"secret": settings.EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
		"test": settings.EXCHANGE_CONFIG["mode"] == "testnet",
		"adjustForTimeDifference": True,
	})

	if settings.EXCHANGE_CONFIG["mode"] == "testnet" and hasattr(exchange, "urls"):
		if "test" in exchange.urls:
			exchange.urls["api"] = exchange.urls["test"]

	trading_mode = settings.TRADING_MODE
	if trading_mode == "futures":
		exchange.options["defaultType"] = "linear"
	else:
		exchange.options["defaultType"] = "spot"

	return exchange

# --- ERROR HANDLER ---
def format_ccxt_error(e: Exception) -> str:
	err_type = e.__class__.__name__
	err_msg = str(e)

	if "InsufficientFunds" in err_type or "balance" in err_msg.lower():
		return f"Недостаточный баланс: {err_msg}"
	elif "InvalidOrder" in err_type or "symbol" in err_msg.lower():
		return f"Неверный символ или параметры ордера: {err_msg}"
	elif "NetworkError" in err_type or "Connection" in err_msg:
		return f"Ошибка сети/подключения: {err_msg}"
	else:
		return f"{err_type}: {err_msg}"

# --- BALANCE ---
async def get_balance(currency: str = "USDT"):
	try:
		exchange = get_exchange()
		balance = await exchange.fetch_balance()
		return balance["free"].get(currency, 0.0)
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Balance error: {msg}")
		return 0.0

# --- CREATE ORDER ---
async def create_order(
	symbol: str,
	side: str,
	amount: float = None,
	price: float = None,
	risk_service: RiskService = None,
	telegram: TelegramService = None,
	signal_strength: float = None,
	order_type: str = "market",   # market, limit, stopMarket, takeProfit
	reduce_only: bool = False,    # поддержка reduceOnly
	take_profit: float | None = None,
	stop_price: float | None = None
	):
	try:
		exchange = get_exchange()
		trading_mode = settings.TRADING_MODE

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")
			strength = signal_strength if signal_strength else 1.0

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=strength
			)

			valid = await risk_service.validate_trade(
					symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					open_trades=1,
					total_loss_pct=total_loss_pct,
					strength=strength
			)
			if not valid:
					if telegram:
						await telegram.send_message(f"❌ Risk validation failed for {symbol}")
					return {"error": "Risk validation failed"}

			amount = position_size

		# --- Создание ордера ---
		params = {"reduceOnly": reduce_only}

		if trading_mode == "futures":
			leverage = risk_service.calculate_leverage(symbol, signal_strength or 1.0) if risk_service else 1
			await exchange.set_leverage(leverage, symbol)

			if order_type == "limit" and price:
					order = await exchange.create_limit_order(symbol, side, amount, price, params=params)
			elif order_type == "market":
					order = await exchange.create_market_order(symbol, side, amount, params=params)
			elif order_type == "stopMarket" and stop_price:
					params.update({"stopPrice": stop_price})
					order = await exchange.create_order(symbol, side, order_type, amount, params=params)
			elif order_type == "takeProfit" and take_profit:
					params.update({"takeProfitPrice": take_profit})
					order = await exchange.create_order(symbol, side, order_type, amount, params=params)
			else:
					order = await exchange.create_market_order(symbol, side, amount, params=params)

		else:  # spot/testnet
			if order_type == "limit" and price:
					order = await exchange.create_limit_order(symbol, side, amount, price)
			else:
					order = await exchange.create_market_order(symbol, side, amount)

		if risk_service:
			trade = TradeORM(
					symbol=symbol,
					side=side,
					amount=amount,
					price=price or 0.0,
					status="open",
					exchange_order_id=order.get("id")
			)
			risk_service.db_session.add(trade)
			await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(
					f"✅ Order created: {symbol} {side} {amount}, type={order_type}, reduceOnly={reduce_only}"
			)

		return order
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Order error: {msg}")
		if telegram:
			await telegram.send_message(f"❌ Order failed: {msg}")
		return {"error": msg}

# --- CANCEL ORDER ---
async def cancel_order(symbol: str, order_id: str, risk_service: RiskService = None, telegram: TelegramService = None):
	try:
		exchange = get_exchange()
		result = await exchange.cancel_order(order_id, symbol)

		if risk_service:
			stmt = select(TradeORM).where(TradeORM.exchange_order_id == order_id)
			trade = (await risk_service.db_session.execute(stmt)).scalar_one_or_none()
			if trade:
					trade.status = "canceled"
					await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(f"⚠️ Order canceled: {order_id}")
		return result
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Cancel error: {msg}")
		return {"error": msg}

# --- GET POSITIONS ---
async def get_positions(symbol: str = None):
	try:
		exchange = get_exchange()
		trading_mode = settings.TRADING_MODE

		if trading_mode == "futures":
			if symbol:
					return await exchange.fetch_positions([symbol])
			return await exchange.fetch_positions()
		else:
			return await exchange.fetch_balance()
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Positions error: {msg}")
		return {"error": msg}

# --- GET OPEN ORDERS ---
async def get_open_orders(symbol: str = None):
	try:
		exchange = get_exchange()
		return await exchange.fetch_open_orders(symbol)
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Open orders error: {msg}")
		return {"error": msg}

# --- CLOSE POSITION ---
async def close_position(symbol: str, risk_service: RiskService = None, telegram: TelegramService = None):
	try:
		exchange = get_exchange()
		positions = await exchange.fetch_positions([symbol])
		for pos in positions:
			if pos["contracts"] > 0:
					side = "sell" if pos["side"] == "long" else "buy"
					await exchange.create_market_order(
						symbol, side, pos["contracts"], params={"reduceOnly": True}
					)

					if risk_service and pos.get("id"):
						stmt = select(TradeORM).where(TradeORM.exchange_order_id == pos["id"])
						trade = (await risk_service.db_session.execute(stmt)).scalar_one_or_none()
						if trade:
							trade.status = "closed"
							await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(f"🔒 Position closed: {symbol}")
		return {"status": "closed"}
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Close position error: {msg}")
		return {"error": msg}

# --- TRADE HISTORY ---
async def get_trade_history(symbol: str = None):
	try:
		exchange = get_exchange()
		return await exchange.fetch_my_trades(symbol)
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Trade history error: {msg}")
		return {"error": msg}

# --- SET MARGIN MODE ---
async def set_margin_mode(symbol: str, mode: str = "isolated"):
	try:
		exchange = get_exchange()
		await exchange.set_margin_mode(mode, symbol)
		return {"status": f"Margin mode set to {mode}"}
	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ Margin mode error: {msg}")
		return {"error": msg}


# глобальные переменные для кэша
STRATEGY_CONFIG = {}
CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 минут

async def load_strategies(db: AsyncSession, use_cache: bool = True) -> dict:
	"""
	Загрузить все стратегии из БД и собрать словарь STRATEGY_CONFIG.
	Поддержка нескольких стратегий на один символ и комбинированных индикаторов.
	"""
	global STRATEGY_CONFIG, CACHE_TIMESTAMP

	# --- проверка кэша ---
	if use_cache and STRATEGY_CONFIG and (time.time() - CACHE_TIMESTAMP < CACHE_TTL):
		return STRATEGY_CONFIG

	try:
		result = await db.execute(select(StrategyORM))
		strategies = result.scalars().all()
		config = {}

		for s in strategies:
			# 🔹 поддержка нескольких стратегий на один символ
			if s.symbol not in config:
					config[s.symbol] = []

			strategy_entry = {
					"name": s.symbol + "_" + str(s.id),
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
					"obv_enabled": s.obv_enabled or False,
					"volume_period": s.volume_period or None,
					"vwap_enabled": s.vwap_enabled or False,
					"ichimoku_tenkan": s.ichimoku_tenkan or 9,
					"ichimoku_kijun": s.ichimoku_kijun or 26,
					"ichimoku_senkou": s.ichimoku_senkou or 52,
					"stop_loss": s.stop_loss or 0.02,
					"take_profit_targets": s.take_profit_targets or [0.01, 0.02],
					"take_profit_distribution": s.take_profit_distribution or [],
					"trailing_stop": s.trailing_stop or False,
					"trailing_mode": s.trailing_mode or "none",
					"allocation_percent": s.allocation_percent or 0.05,
					"leverage": s.leverage or 1,
					"strength_multiplier": s.strength_multiplier or 1.0,
					"enabled": s.enabled if hasattr(s, "enabled") else True,
			}

			config[s.symbol].append(strategy_entry)

		STRATEGY_CONFIG = config
		CACHE_TIMESTAMP = time.time()
		logger.info("♻️ Стратегии обновлены из БД")
		return STRATEGY_CONFIG

	except Exception as e:
		logger.error(f"❌ Failed to load strategies: {e}")
		return STRATEGY_CONFIG

async def get_ohlcv(
	db_session: AsyncSession,
	symbol: str,
	timeframe: str = "1h",
	limit: int = 100,
	as_dataframe: bool = True
	):
	"""
	Получение свечей (OHLCV) с биржи.
	timeframe: "1m", "5m", "15m", "1h", "4h", "1d" и т.д.
	- Часовые свечи сохраняем в БД
	- Дневные используем как фильтр (без сохранения)
	- Возврат: DataFrame (по умолчанию) или список словарей
	"""
	try:
		exchange = get_exchange()
		candles = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

		# Преобразуем в DataFrame
		df = pd.DataFrame(
			candles,
			columns=["timestamp", "open", "high", "low", "close", "volume"]
		)

		if timeframe == "1h":
			# Сохраняем часовые свечи в таблицу ohlcv_hourly (bulk insert)
			objects = [
					OHLCVHourly(
						symbol=symbol,
						timestamp=row[0],
						open=row[1],
						high=row[2],
						low=row[3],
						close=row[4],
						volume=row[5],
					)
					for row in candles
			]
			db_session.bulk_save_objects(objects)
			await db_session.commit()
			logger.info(f"✅ Saved {len(candles)} hourly candles for {symbol}")

		else:
			# Для дневных свечей просто возвращаем
			logger.info(f"📊 Loaded {len(candles)} {timeframe} candles for {symbol}")

		# Возврат в нужном формате
		if as_dataframe:
			return df
		else:
			return df.to_dict(orient="records")

	except Exception as e:
		msg = format_ccxt_error(e)
		logger.error(f"❌ OHLCV error for {symbol} {timeframe}: {msg}")
		return {"error": msg}


async def update_ohlcv_for_all_pairs(
	db_session: AsyncSession,
	timeframe: str = "1h",
	limit: int = 500,
	as_dataframe: bool = True
):
	"""
	Массовое обновление OHLCV свечей для всех валютных пар из таблицы strategies.
	- H1 свечи сохраняем в БД
	- D1 свечи используем как фильтр (без сохранения)
	- Возврат: словарь {symbol: DataFrame | list[dict]}
	"""
	try:
		# Загружаем список стратегий из БД
		strategies = await load_strategies(db_session)

		results = {}

		for symbol in strategies.keys():
			candles = await get_ohlcv(
					db_session,
					symbol=symbol,
					timeframe=timeframe,
					limit=limit,
					as_dataframe=as_dataframe
			)

			if isinstance(candles, dict) and "error" in candles:
					logger.error(f"❌ Failed to update OHLCV for {symbol}: {candles['error']}")
					results[symbol] = candles
			else:
					logger.info(f"✅ OHLCV updated for {symbol} ({timeframe})")
					results[symbol] = candles

		return results

	except Exception as e:
		logger.error(f"❌ update_ohlcv_for_all_pairs error: {e}")
		return {"error": str(e)}
