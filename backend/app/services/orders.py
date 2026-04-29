import ccxt
from app.config import EXCHANGE_CONFIG

# Инициализация биржи (Bybit)
def get_exchange():
	exchange_class = getattr(ccxt, EXCHANGE_CONFIG["name"])
	params = {
		"apiKey": EXCHANGE_CONFIG["api_key"],
		"secret": EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
		"test": True,   # важно для Testnet
		"adjustForTimeDifference": True,  # 🔹 синхронизация времени
		"options": {
			"defaultType": "spot",   # или "linear"/"inverse" для деривативов
		}
	}
	return exchange_class(params)


# --- BALANCE ---
def get_balance(currency: str = "USDT"):
	if EXCHANGE_CONFIG["mode"] == "mock":
		if currency == "USDT":
			return 10000.0
		elif currency == "BTC":
			return 1.0
		else:
			return 0.0
	else:
		exchange = get_exchange()
		balance = exchange.fetch_balance()
		return balance["free"].get(currency, 0.0)

# --- ORDERS ---
def create_market_order(symbol: str, side: str, amount: float):
	if EXCHANGE_CONFIG["mode"] == "mock":
		return {"id": "mock-order-001", "symbol": symbol, "side": side, "amount": amount, "status": "filled"}
	else:
		exchange = get_exchange()
		return exchange.create_order(symbol=symbol, type="market", side=side, amount=amount)

def create_limit_order(symbol: str, side: str, amount: float, price: float):
	if EXCHANGE_CONFIG["mode"] == "mock":
		return {"id": "mock-order-002", "symbol": symbol, "side": side, "amount": amount, "price": price, "status": "open"}
	else:
		exchange = get_exchange()
		return exchange.create_order(symbol=symbol, type="limit", side=side, amount=amount, price=price)

def cancel_order(symbol: str, order_id: str):
	if EXCHANGE_CONFIG["mode"] == "mock":
		return {"id": order_id, "symbol": symbol, "status": "canceled"}
	else:
		exchange = get_exchange()
		return exchange.cancel_order(order_id, symbol)

def get_order(symbol: str, order_id: str):
	if EXCHANGE_CONFIG["mode"] == "mock":
		return {"id": order_id, "symbol": symbol, "status": "mock-info"}
	else:
		exchange = get_exchange()
		return exchange.fetch_order(order_id, symbol)

def get_open_orders(symbol: str):
	if EXCHANGE_CONFIG["mode"] == "mock":
		return [{"id": "mock-order-002", "symbol": symbol, "side": "buy", "amount": 0.001, "status": "open"}]
	else:
		exchange = get_exchange()
		return exchange.fetch_open_orders(symbol)

# --- MARKET DATA ---
def get_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 100):
	exchange = get_exchange()
	return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

def get_ticker(symbol: str):
	exchange = get_exchange()
	return exchange.fetch_ticker(symbol)
