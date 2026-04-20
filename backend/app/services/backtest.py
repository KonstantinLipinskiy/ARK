import pandas as pd
from app.services import indicators, risk
from app.config import STRATEGY_CONFIG

def backtest_strategy(data: pd.DataFrame, pair: str):
	"""
	Универсальный бэктест по настройкам из STRATEGY_CONFIG
	data: DataFrame с колонками ['open','high','low','close','volume']
	pair: строка, например "BTC/USDT"
	"""
	config = STRATEGY_CONFIG[pair]
	trades = []
	position = None

	# Считаем индикаторы, которые включены
	if "EMA" in config["enabled_indicators"]:
		data["ema_short"] = indicators.ema(data["close"], config["ema_short"])
		data["ema_long"] = indicators.ema(data["close"], config["ema_long"])

	if "RSI" in config["enabled_indicators"]:
		data["rsi"] = indicators.rsi(data["close"], config["rsi_period"])

	if "MACD" in config["enabled_indicators"]:
		macd_line, signal_line = indicators.macd(
			data["close"], config["macd_fast"], config["macd_slow"], config["macd_signal"]
		)
		data["macd_line"], data["macd_signal"] = macd_line, signal_line

	if "Bollinger" in config["enabled_indicators"]:
		upper, sma, lower = indicators.bollinger(data["close"], config["bollinger_period"])
		data["boll_upper"], data["boll_sma"], data["boll_lower"] = upper, sma, lower

	if "ATR" in config["enabled_indicators"]:
		data["atr"] = indicators.atr(data["high"], data["low"], data["close"], config["atr_period"])

	if "OBV" in config["enabled_indicators"]:
		data["obv"] = indicators.obv(data["close"], data["volume"])

	if "Stochastic" in config["enabled_indicators"]:
		data["stoch_k"], data["stoch_d"] = indicators.stochastic(
			data["high"], data["low"], data["close"], config["stochastic_period"]
		)

	if "Volume" in config["enabled_indicators"]:
		data["vol_sma"] = data["volume"].rolling(window=20).mean()

	# Основной цикл по свечам
	for i in range(1, len(data)):  # начинаем с 1, чтобы был доступ к i-1 для OBV
		row = data.iloc[i]

		# Фильтр по OBV
		if "OBV" in config["enabled_indicators"]:
			if row["obv"] <= data["obv"].iloc[i-1]:
					continue

		# Фильтр по Volume
		if "Volume" in config["enabled_indicators"]:
			if row["volume"] < row["vol_sma"]:
					continue

		# Вход по EMA crossover
		if position is None and "EMA" in config["enabled_indicators"]:
			if row["ema_short"] > row["ema_long"]:
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"])
					tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"])
					position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open"}

		# Вход по RSI
		if position is None and "RSI" in config["enabled_indicators"]:
			if row["rsi"] < 30:
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"])
					tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"])
					position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open"}

		# Вход по MACD
		if position is None and "MACD" in config["enabled_indicators"]:
			if row["macd_line"] > row["macd_signal"]:
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"])
					tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"])
					position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open"}

		# Вход по Bollinger
		if position is None and "Bollinger" in config["enabled_indicators"]:
			if row["close"] <= row["boll_lower"]:
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"])
					tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"])
					position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open"}

		# Вход по Stochastic
		if position is None and "Stochastic" in config["enabled_indicators"]:
			if row["stoch_k"] < 20 and row["stoch_k"] > row["stoch_d"]:
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"])
					tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"])
					position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open"}

		# Проверка открытой позиции
		elif position is not None:
			price = row["close"]

			# Стоп-лосс
			if price <= position["stop"]:
					position["exit"] = price
					position["status"] = "stopped"
					trades.append(position)
					position = None

			# Динамический стоп по ATR
			elif "ATR" in config["enabled_indicators"]:
					atr_value = row["atr"]
					dynamic_stop = position["entry"] - 2 * atr_value
					if price <= dynamic_stop:
						position["exit"] = price
						position["status"] = "atr_stop"
						trades.append(position)
						position = None

			# Тейк-профит
			elif price >= position["tp"][0]:
					position["exit"] = price
					position["status"] = "take_profit"
					trades.append(position)

					if config.get("trailing_stop", False):
						if config.get("trailing_mode") == "step":
							position["stop"] = position["entry"]
						elif config.get("trailing_mode") == "percent":
							position["stop"] = price * (1 - config["stop_loss"])

					position["tp"].pop(0)
					if len(position["tp"]) == 0:
						position = None

			# Альтернативный выход по RSI
			elif "RSI" in config["enabled_indicators"] and row.get("rsi", 50) > 70:
					position["exit"] = price
					position["status"] = "rsi_exit"
					trades.append(position)
					position = None

			# Альтернативный выход по Stochastic
			elif "Stochastic" in config["enabled_indicators"]:
					if row["stoch_k"] > 80 and row["stoch_k"] < row["stoch_d"]:
						position["exit"] = price
						position["status"] = "stoch_exit"
						trades.append(position)
						position = None

	return trades

# Пример запуска
if __name__ == "__main__":
	df = pd.read_csv("data/BTCUSDT_1h.csv")
	results = backtest_strategy(df, "BTC/USDT")
	print(f"Всего сделок: {len(results)}")
	for trade in results[:5]:
		print(trade)
