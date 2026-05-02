import ccxt.async_support as ccxt
from app.config import EXCHANGE_CONFIG
from app.utils.logger import logger
from app.services.risk import RiskService
from app.services.telegram import TelegramService
from app.db.schemas import TradeORM

# --- INIT ---
def get_exchange():
	exchange_class = getattr(ccxt, EXCHANGE_CONFIG["name"])
	params = {
		"apiKey": EXCHANGE_CONFIG["api_key"],
		"secret": EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
		"test": EXCHANGE_CONFIG["mode"] == "testnet",
		"adjustForTimeDifference": True,
		"options": {"defaultType": EXCHANGE_CONFIG["market_type"]},
	}
	return exchange_class(params)

# --- BALANCE ---
async def get_balance(currency: str = "USDT"):
	try:
		exchange = get_exchange()
		balance = await exchange.fetch_balance()
		return balance["free"].get(currency, 0.0)
	except Exception as e:
		logger.error(f"❌ Balance error: {e}")
		return 0.0

# --- ORDERS ---
async def create_order(
	symbol: str,
	side: str,
	amount: float,
	order_type: str = "market",
	price: float = None,
	stop_price: float = None,
	risk_service: RiskService = None,
	telegram: TelegramService = None
):
	try:
		# Проверка риска
		if risk_service:
			valid = await risk_service.validate_trade(
					symbol,
					deposit=1000,
					entry_price=price or 0,
					stop_loss_pct=0.02,
					open_trades=1,
					total_loss_pct=0.01
			)
			if not valid:
					return {"error": "Risk validation failed"}

		exchange = get_exchange()
		params = {}
		if stop_price:
			params["stopPrice"] = stop_price

		order = await exchange.create_order(
			symbol=symbol,
			type=order_type,
			side=side,
			amount=amount,
			price=price,
			params=params
		)

		# Сохраняем в БД
		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=price or 0.0,
			status="open"
		)
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		# Уведомление в Telegram
		if telegram:
			await telegram.send_message(f"✅ Order created: {symbol} {side} {amount} {order_type}")

		return order
	except Exception as e:
		logger.error(f"❌ Order error: {e}")
		if telegram:
			await telegram.send_message(f"❌ Order failed: {e}")
		return {"error": str(e)}

# --- STOP ORDER ---
async def create_stop_order(
	symbol: str,
	side: str,
	amount: float,
	stop_price: float,
	order_type: str = "stop_market",
	risk_service: RiskService = None,
	telegram: TelegramService = None
):
	try:
		if risk_service:
			valid = await risk_service.validate_trade(symbol, deposit=1000, entry_price=stop_price, stop_loss_pct=0.02, open_trades=1, total_loss_pct=0.01)
			if not valid:
					return {"error": "Risk validation failed"}

		exchange = get_exchange()
		params = {"stopPrice": stop_price}
		order = await exchange.create_order(symbol, order_type, side, amount, None, params)

		trade = TradeORM(symbol=symbol, side=side, amount=amount, price=stop_price, status="open")
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(f"📌 Stop order created: {symbol} {side} {amount} @ {stop_price}")

		return order
	except Exception as e:
		logger.error(f"❌ Stop order error: {e}")
		return {"error": str(e)}

# --- OCO ORDER ---
async def create_oco_order(
	symbol: str,
	side: str,
	amount: float,
	price: float,
	stop_price: float,
	risk_service: RiskService = None,
	telegram: TelegramService = None
):
	try:
		exchange = get_exchange()
		params = {
			"type": "oco",
			"price": price,
			"stopPrice": stop_price
		}
		order = await exchange.create_order(symbol, "limit", side, amount, price, params)

		trade = TradeORM(symbol=symbol, side=side, amount=amount, price=price, status="open")
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(f"🔀 OCO order created: {symbol} {side} {amount} TP={price}, SL={stop_price}")

		return order
	except Exception as e:
		logger.error(f"❌ OCO order error: {e}")
		return {"error": str(e)}

# --- FUTURES ORDER ---
async def create_futures_order(
	symbol: str,
	side: str,
	amount: float,
	leverage: int = 1,
	order_type: str = "market",
	price: float = None,
	reduce_only: bool = False,
	margin_type: str = "isolated",
	risk_service: RiskService = None,
	telegram: TelegramService = None
):
	try:
		if risk_service:
			valid = await risk_service.validate_trade(symbol, deposit=1000, entry_price=price or 0, stop_loss_pct=0.02, open_trades=1, total_loss_pct=0.01)
			if not valid:
					return {"error": "Risk validation failed"}

		exchange = get_exchange()
		await exchange.set_leverage(leverage, symbol)

		params = {
			"reduceOnly": reduce_only,
			"marginType": margin_type
		}

		order = await exchange.create_order(symbol, order_type, side, amount, price, params)

		trade = TradeORM(symbol=symbol, side=side, amount=amount, price=price or 0.0, status="open")
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		if telegram:
			await telegram.send_message(f"⚡ Futures order created: {symbol} {side} {amount} x{leverage}")

		return order
	except Exception as e:
		logger.error(f"❌ Futures order error: {e}")
		return {"error": str(e)}

# --- CANCEL ORDER ---
async def cancel_order(symbol: str, order_id: str, telegram: TelegramService = None):
	try:
		exchange = get_exchange()
		result = await exchange.cancel_order(order_id, symbol)
		if telegram:
			await telegram.send_message(f"⚠️ Order canceled: {order_id}")
		return result
	except Exception as e:
		logger.error(f"❌ Cancel error: {e}")
		return {"error": str(e)}

# --- MARKET DATA ---
async def get_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 100):
	exchange = get_exchange()
	return await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

async def get_ticker(symbol: str):
	exchange = get_exchange()
	return await exchange.fetch_ticker(symbol)
