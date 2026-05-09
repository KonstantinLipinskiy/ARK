import ccxt.async_support as ccxt
from app.config import settings
from app.utils.logger import logger
from app.services.risk import RiskService
from app.services.telegram import TelegramService
from app.db.schemas import TradeORM
from sqlalchemy import select
import asyncio

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
