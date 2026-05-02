import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import asyncio
from app.services import indicators, risk
from app.config import STRATEGY_CONFIG, settings
from app.db.schemas import TradeORM, BacktestReport
from app.utils.logger import logger
from app.db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession


# --- Основной бэктест ---
async def backtest_strategy(data: pd.DataFrame, pair: str, strategy_name: str = "default"):
	config = STRATEGY_CONFIG[pair]
	trades = []
	position = None
	market_type = settings.EXCHANGE_CONFIG["market_type"]  # spot или futures

	# --- Индикаторы ---
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
		data["stoch_k"] = indicators.stochastic(data["close"], data["high"], data["low"], config["stochastic_period"])
		data["stoch_d"] = data["stoch_k"].rolling(window=3).mean()

	if "Volume" in config["enabled_indicators"]:
		data["vol_sma"] = data["volume"].rolling(window=20).mean()

	# --- Основной цикл по свечам ---
	for i in range(1, len(data)):
		row = data.iloc[i]

		# Фильтры
		if "OBV" in config["enabled_indicators"] and row["obv"] <= data["obv"].iloc[i-1]:
			continue
		if "Volume" in config["enabled_indicators"] and row["volume"] < row["vol_sma"]:
			continue

		# Входы по условиям из entry_conditions
		if position is None and "entry_conditions" in config:
			for condition in config["entry_conditions"]:
					signals = []
					direction = None  # long или short

					for ind in condition:
						if ind == "EMA":
							if row["ema_short"] > row["ema_long"]:
									signals.append(True); direction = "long"
							elif row["ema_short"] < row["ema_long"] and market_type == "futures":
									signals.append(True); direction = "short"
							else:
									signals.append(False)

						elif ind == "RSI":
							if row["rsi"] < 30:
									signals.append(True); direction = "long"
							elif row["rsi"] > 70 and market_type == "futures":
									signals.append(True); direction = "short"
							else:
									signals.append(False)

						elif ind == "MACD":
							if row["macd_line"] > row["macd_signal"]:
									signals.append(True); direction = "long"
							elif row["macd_line"] < row["macd_signal"] and market_type == "futures":
									signals.append(True); direction = "short"
							else:
									signals.append(False)

						elif ind == "Bollinger":
							if row["close"] <= row["boll_lower"]:
									signals.append(True); direction = "long"
							elif row["close"] >= row["boll_upper"] and market_type == "futures":
									signals.append(True); direction = "short"
							else:
									signals.append(False)

						elif ind == "Stochastic":
							if row["stoch_k"] < 20 and row["stoch_k"] > row["stoch_d"]:
									signals.append(True); direction = "long"
							elif row["stoch_k"] > 80 and row["stoch_k"] < row["stoch_d"] and market_type == "futures":
									signals.append(True); direction = "short"
							else:
									signals.append(False)

					if all(signals):
						entry_price = row["close"]
						stop_price = risk.apply_stop_loss(entry_price, config["stop_loss"], direction)
						tp_levels = risk.apply_take_profit(entry_price, config["take_profit_targets"], direction)
						position = {"entry": entry_price, "stop": stop_price, "tp": tp_levels, "status": "open", "side": direction}
						break

		# --- Управление позицией ---
		elif position is not None:
			price = row["close"]

			if position["side"] == "long":
					if price <= position["stop"]:
						position["exit"] = price; position["status"] = "stopped"
						trades.append(position); position = None
					elif "ATR" in config["enabled_indicators"]:
						atr_value = row["atr"]
						dynamic_stop = position["entry"] - 2 * atr_value
						if price <= dynamic_stop:
							position["exit"] = price; position["status"] = "atr_stop"
							trades.append(position); position = None
					elif price >= position["tp"][0]:
						position["exit"] = price; position["status"] = "take_profit"
						trades.append(position); position["tp"].pop(0)
						if len(position["tp"]) == 0: position = None

			elif position["side"] == "short":
					if price >= position["stop"]:
						position["exit"] = price; position["status"] = "stopped"
						trades.append(position); position = None
					elif "ATR" in config["enabled_indicators"]:
						atr_value = row["atr"]
						dynamic_stop = position["entry"] + 2 * atr_value
						if price >= dynamic_stop:
							position["exit"] = price; position["status"] = "atr_stop"
							trades.append(position); position = None
					elif price <= position["tp"][0]:
						position["exit"] = price; position["status"] = "take_profit"
						trades.append(position); position["tp"].pop(0)
						if len(position["tp"]) == 0: position = None

	return trades


# --- Метрики ---
def calculate_metrics(trades):
	if not trades:
		return {"winrate": 0, "avg_profit": 0, "max_drawdown": 0, "sharpe": 0}

	profits = [t["exit"] - t["entry"] for t in trades if "exit" in t]
	wins = [p for p in profits if p > 0]
	losses = [p for p in profits if p <= 0]

	winrate = len(wins) / len(trades) * 100
	avg_profit = np.mean(profits)
	max_drawdown = np.min(profits)
	sharpe = (np.mean(profits) / np.std(profits)) * np.sqrt(252) if np.std(profits) > 0 else 0

	return {
		"winrate": round(winrate, 2),
		"avg_profit": round(avg_profit, 4),
		"max_drawdown": round(max_drawdown, 4),
		"sharpe": round(sharpe, 2)
	}

# --- Сохранение сделок в БД ---
async def save_trades_to_db(trades, pair: str, strategy_name: str = "default", user_id: int = 1):
	async with get_session() as session:
		for t in trades:
			trade = TradeORM(
					symbol=pair,
					side="buy",
					amount=1.0,
					price=t["entry"],
					status=t["status"],
					user_id=user_id
			)
			session.add(trade)
		await session.commit()

# --- Сохранение метрик в БД ---
async def save_metrics_to_db(metrics: dict, pair: str, strategy_name: str = "default", user_id: int = 1):
	async with get_session() as session:
		report = BacktestReport(
			symbol=pair,
			strategy=strategy_name,
			winrate=metrics["winrate"],
			avg_profit=metrics["avg_profit"],
			max_drawdown=metrics["max_drawdown"],
			sharpe=metrics["sharpe"],
			user_id=user_id
		)
		session.add(report)
		await session.commit()

# --- Визуализация ---
def plot_backtest(data: pd.DataFrame, trades: list, pair: str):
	plt.figure(figsize=(12,6))
	plt.plot(data["close"], label="Close Price")
	for t in trades:
		plt.axvline(x=data.index[data["close"] == t["entry"]][0], color="green", linestyle="--", label="Entry")
		if "exit" in t:
			plt.axvline(x=data.index[data["close"] == t["exit"]][0], color="red", linestyle="--", label="Exit")
	plt.title(f"Backtest {pair}")
	plt.legend()
	plt.show()

# --- Пример запуска ---
if __name__ == "__main__":
	df = pd.read_csv("data/BTCUSDT_1h.csv")
	loop = asyncio.get_event_loop()
	results = loop.run_until_complete(backtest_strategy(df, "BTC/USDT"))
	metrics = calculate_metrics(results)

	print(f"Всего сделок: {len(results)}")
	print("Метрики:", metrics)
	for trade in results[:5]:
		print(trade)

	# Сохранение в БД
	loop.run_until_complete(save_trades_to_db(results, "BTC/USDT", strategy_name="EMA+RSI"))
	loop.run_until_complete(save_metrics_to_db(metrics, "BTC/USDT", strategy_name="EMA+RSI"))

	# Визуализация
	plot_backtest(df, results, "BTC/USDT")
