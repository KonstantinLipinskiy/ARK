# test_orders.py
import pprint
from app.services import orders

def main():
	print("=== Тест подключения к Bybit Testnet ===")

	# 1. Проверка баланса
	usdt_balance = orders.get_balance("USDT")
	print(f"Баланс USDT: {usdt_balance}")

	# 2. Создание тестового рыночного ордера (пример: покупка BTCUSDT)
	try:
		order = orders.create_market_order(symbol="BTC/USDT", side="buy", amount=0.001)
		print("Создан рыночный ордер:")
		pprint.pprint(order)
	except Exception as e:
		print("Ошибка при создании ордера:", e)

	# 3. Получение открытых ордеров
	try:
		open_orders = orders.get_open_orders("BTC/USDT")
		print("Открытые ордера:")
		pprint.pprint(open_orders)
	except Exception as e:
		print("Ошибка при получении открытых ордеров:", e)

	# 4. Получение тикера
	try:
		ticker = orders.get_ticker("BTC/USDT")
		print("Текущий тикер BTC/USDT:")
		pprint.pprint(ticker)
	except Exception as e:
		print("Ошибка при получении тикера:", e)

if __name__ == "__main__":
	main()
