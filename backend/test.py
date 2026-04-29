# import ccxt

# exchange = ccxt.bybit({
# 	"apiKey": "H5nVi061CyaLHRB1H0",
# 	"secret": "JrjHGRClxvOzR34nrIOddPZ4wYAM9422t6AC",
# 	"enableRateLimit": True,
# 	"test": True,
# 	"adjustForTimeDifference": True,
# 	"options": {"defaultType": "unified"},
# 	"urls": {
# 		"api": {
# 			"public": "https://api-testnet.bybit.com",
# 			"private": "https://api-testnet.bybit.com"
# 		}
# 	}
# })

# print(exchange.fetch_balance())
# print(exchange.fetch_balance({'type': 'unified', 'code': 'USDT'}))
# print(exchange.fetch_balance({'type': 'unified', 'code': 'BTC'}))


# import ccxt
# import pprint

# exchange = ccxt.bybit({
#     "apiKey": "H5nVi061CyaLHRB1H0",
#     "secret": "JrjHGRClxvOzR34nrIOddPZ4wYAM9422t6AC",
#     "enableRateLimit": True,
#     "test": True,
#     "adjustForTimeDifference": True,
#     "options": {"defaultType": "unified"},
#     "urls": {
#         "api": {
#             "public": "https://api-testnet.bybit.com",
#             "private": "https://api-testnet.bybit.com"
#         }
#     }
# })


# balance = exchange.private_get_v5_account_wallet_balance({
#     "accountType": "UNIFIED"
# })
# pprint.pprint(balance)

import ccxt

exchange = ccxt.bybit({
    "apiKey": "H5nVi061CyaLHRB1H0",
    "secret": "JrjHGRClxvOzR34nrIOddPZ4wYAM9422t6AC",
    "enableRateLimit": True,
    "test": True,
    "adjustForTimeDifference": True,
    "options": {"defaultType": "unified"},
    "urls": {
        "api": {
            "public": "https://api-testnet.bybit.com",
            "private": "https://api-testnet.bybit.com"
        }
    }
})

symbol = "BTC/USDT"
amount = 0.001   # покупаем 0.001 BTC
order = exchange.create_market_buy_order(symbol, amount)

print("Создан ордер:", order)

# Проверим открытые ордера
open_orders = exchange.fetch_open_orders(symbol)
print("Открытые ордера:", open_orders)
