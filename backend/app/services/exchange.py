import ccxt.async_support as ccxt
from app.config import EXCHANGE_CONFIG, STRATEGY_CONFIG
from app.utils.logger import logger
from app.services.risk import RiskService
from app.services.telegram import TelegramService

# --- INIT ---
def get_exchange():
	"""
	Инициализация клиента биржи через ccxt.
	"""
	exchange_class = getattr(ccxt, EXCHANGE_CONFIG["name"])
	exchange = exchange_class({
		"apiKey": EXCHANGE_CONFIG["api_key"],
		"secret": EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
		"test": EXCHANGE_CONFIG["mode"] == "testnet",
		"adjustForTimeDifference": True,
	})

	# Если режим testnet — переопределяем URL
	if EXCHANGE_CONFIG["mode"] == "testnet" and hasattr(exchange, "urls"):
		if "test" in exchange.urls:
			exchange.urls["api"] = exchange.urls["test"]

	# Устанавливаем тип торговли (spot/futures)
	market_type = EXCHANGE_CONFIG.get("market_type", "spot")
	if market_type == "futures":
		exchange.options["defaultType"] = "linear"  # USDT‑margined futures
	else:
		exchange.options["defaultType"] = "spot"

	return exchange

# --- BALANCE ---
async def get_balance(currency: str = "USDT"):
	try:
		exchange = get_exchange()
		balance = await exchange.fetch_balance()
		return balance["free"].get(currency, 0.0)
	except Exception as e:
		logger.error(f"❌ Balance error: {e}")
		return 0.0

# --- CREATE ORDER ---
async def create_order(
	symbol: str,
	side: str,
	amount: float,
	price: float = None,
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
					if telegram:
						await telegram.send_message(f"❌ Risk validation failed for {symbol}")
					return {"error": "Risk validation failed"}

		exchange = get_exchange()
		market_type = EXCHANGE_CONFIG.get("market_type", "spot")

		if market_type == "spot":
			if price:
					order = await exchange.create_limit_order(symbol, side, amount, price)
			else:
					order = await exchange.create_market_order(symbol, side, amount)

		elif market_type == "futures":
			leverage = STRATEGY_CONFIG.get(symbol, {}).get("leverage", 1)
			await exchange.set_leverage(leverage, symbol)

			if price:
					order = await exchange.create_limit_order(symbol, side, amount, price, params={"reduceOnly": False})
			else:
					order = await exchange.create_market_order(symbol, side, amount, params={"reduceOnly": False})

		if telegram:
			await telegram.send_message(f"✅ Order created: {symbol} {side} {amount}")

		return order
	except Exception as e:
		logger.error(f"❌ Order error: {e}")
		if telegram:
			await telegram.send_message(f"❌ Order failed: {e}")
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

# --- GET POSITIONS ---
async def get_positions(symbol: str = None):
	try:
		exchange = get_exchange()
		market_type = EXCHANGE_CONFIG.get("market_type", "spot")

		if market_type == "futures":
			if symbol:
					return await exchange.fetch_positions([symbol])
			return await exchange.fetch_positions()
		else:
			return await exchange.fetch_balance()
	except Exception as e:
		logger.error(f"❌ Positions error: {e}")
		return {"error": str(e)}

# --- GET OPEN ORDERS ---
async def get_open_orders(symbol: str = None):
	try:
		exchange = get_exchange()
		return await exchange.fetch_open_orders(symbol)
	except Exception as e:
		logger.error(f"❌ Open orders error: {e}")
		return {"error": str(e)}

# --- CLOSE POSITION ---
async def close_position(symbol: str, telegram: TelegramService = None):
	try:
		exchange = get_exchange()
		positions = await exchange.fetch_positions([symbol])
		for pos in positions:
			if pos["contracts"] > 0:
					side = "sell" if pos["side"] == "long" else "buy"
					await exchange.create_market_order(symbol, side, pos["contracts"], params={"reduceOnly": True})
		if telegram:
			await telegram.send_message(f"🔒 Position closed: {symbol}")
		return {"status": "closed"}
	except Exception as e:
		logger.error(f"❌ Close position error: {e}")
		return {"error": str(e)}

# --- TRADE HISTORY ---
async def get_trade_history(symbol: str = None):
	try:
		exchange = get_exchange()
		return await exchange.fetch_my_trades(symbol)
	except Exception as e:
		logger.error(f"❌ Trade history error: {e}")
		return {"error": str(e)}

# --- SET MARGIN MODE ---
async def set_margin_mode(symbol: str, mode: str = "isolated"):
	try:
		exchange = get_exchange()
		await exchange.set_margin_mode(mode, symbol)
		return {"status": f"Margin mode set to {mode}"}
	except Exception as e:
		logger.error(f"❌ Margin mode error: {e}")
		return {"error": str(e)}
