import ccxt
from app.config import EXCHANGE_CONFIG, STRATEGY_CONFIG

def get_exchange():
	"""
	Инициализация клиента биржи через ccxt.
	"""
	exchange_class = getattr(ccxt, EXCHANGE_CONFIG["name"])
	exchange = exchange_class({
		"apiKey": EXCHANGE_CONFIG["api_key"],
		"secret": EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
	})

	# Если режим testnet — переопределяем URL
	if EXCHANGE_CONFIG["mode"] == "testnet" and hasattr(exchange, "urls"):
		if "test" in exchange.urls:
			exchange.urls["api"] = exchange.urls["test"]

	return exchange


def create_order(symbol, side, amount, price=None):
	"""
	Создание ордера в зависимости от market_type (spot/futures).
	"""
	exchange = get_exchange()
	market_type = STRATEGY_CONFIG[symbol].get("market_type", "spot")

	if market_type == "spot":
		# Спотовый ордер
		if price:
			return exchange.create_limit_order(symbol, side, amount, price)
		else:
			return exchange.create_market_order(symbol, side, amount)

	elif market_type == "futures":
		leverage = STRATEGY_CONFIG[symbol].get("leverage", 1)
		exchange.set_leverage(leverage, symbol)

		# Фьючерсный ордер
		if price:
			return exchange.create_limit_order(symbol, side, amount, price, params={"type": "future"})
		else:
			return exchange.create_market_order(symbol, side, amount, params={"type": "future"})


def get_balance():
	"""
	Получение баланса аккаунта.
	"""
	exchange = get_exchange()
	return exchange.fetch_balance()


def get_positions(symbol=None):
	"""
	Получение открытых позиций (актуально для фьючерсов).
	"""
	exchange = get_exchange()
	if symbol:
		return exchange.fetch_positions([symbol])
	return exchange.fetch_positions()
