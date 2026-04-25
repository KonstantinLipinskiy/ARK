import ccxt
from app.config import EXCHANGE_CONFIG

# Инициализация биржи (например, Binance)
def get_exchange():
	exchange_class = getattr(ccxt, EXCHANGE_CONFIG["name"])
	return exchange_class({
		"apiKey": EXCHANGE_CONFIG["api_key"],
		"secret": EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
	})

# Выставление рыночного ордера
def create_market_order(symbol: str, side: str, amount: float):
	exchange = get_exchange()
	order = exchange.create_order(
		symbol=symbol,
		type="market",
		side=side,
		amount=amount
	)
	return order

# Выставление лимитного ордера
def create_limit_order(symbol: str, side: str, amount: float, price: float):
	exchange = get_exchange()
	order = exchange.create_order(
		symbol=symbol,
		type="limit",
		side=side,
		amount=amount,
		price=price
	)
	return order

# Отмена ордера
def cancel_order(symbol: str, order_id: str):
	exchange = get_exchange()
	return exchange.cancel_order(order_id, symbol)

# Получение информации об ордере
def get_order(symbol: str, order_id: str):
	exchange = get_exchange()
	return exchange.fetch_order(order_id, symbol)

# Получение открытых ордеров
def get_open_orders(symbol: str):
	exchange = get_exchange()
	return exchange.fetch_open_orders(symbol)

# Получение баланса (по умолчанию USDT)
def get_balance(currency: str = "USDT"):
	exchange = get_exchange()
	balance = exchange.fetch_balance()
	return balance["free"].get(currency, 0.0)

# Получение свечей (OHLCV)
def get_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 100):
	exchange = get_exchange()
	return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

# Получение тикера (текущая цена и данные)
def get_ticker(symbol: str):
	exchange = get_exchange()
	return exchange.fetch_ticker(symbol)
