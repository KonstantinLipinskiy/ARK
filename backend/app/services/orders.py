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
