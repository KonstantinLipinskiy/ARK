import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import asyncio
from datetime import datetime
from app.services import indicators, risk
from app.services.ml import MLService
from app.config import settings
from app.db.schemas import TradeORM, BacktestReport
from app.utils.logger import logger
from app.db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.strategy_service import load_strategies  # 🔹 новый импорт

# --- ML Service ---
ml_service = MLService()
ml_service.load_model("models/sklearn_model.pkl", model_type="sklearn")

def build_features(row: pd.Series) -> dict:
	"""Формируем признаки для ML модели из строки DataFrame."""
	return {
		"ema": row.get("ema_short", 0),
		"rsi": row.get("rsi", 50),
		"macd": row.get("macd_line", 0),
		"hour": datetime.utcnow().hour,
		"atr": row.get("atr", 0)
	}

# --- Основной бэктест ---
async def backtest_strategy(data: pd.DataFrame, pair: str, strategy_name: str = "default", session: AsyncSession = None):
	# 🔹 Загружаем стратегию из БД
	strategies = await load_strategies(session)
	config = strategies[pair]

	trades = []
	position = None
	market_type = settings.TRADING_MODE  # spot / futures / testnet

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
					direction = None

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

						features = build_features(row)
						probability = ml_service.predict_signal(features)
						signal_strength = probability * 2

						leverage = risk.calculate_leverage(pair, signal_strength)

						deposit = 1000
						amount = await risk.calculate_position_size(
							symbol=pair,
							deposit=deposit,
							entry_price=entry_price,
							stop_loss_pct=config["stop_loss"],
							strength=signal_strength
						)

						position = {
							"entry": entry_price,
							"stop": stop_price,
							"tp": tp_levels,
							"status": "open",
							"side": direction,
							"amount": amount,
							"leverage": leverage
						}
						break

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
def calculate_metrics(trades, initial_deposit=1000):
	if not trades:
		return {"winrate": 0, "avg_profit": 0, "max_drawdown": 0, "sharpe": 0}

	profits = [(t["exit"] - t["entry"]) * t.get("amount", 1.0) * t.get("leverage", 1) for t in trades if "exit" in t]
	equity_curve = np.cumsum(profits) + initial_deposit

	peak = np.maximum.accumulate(equity_curve)
	drawdowns = (equity_curve - peak) / peak
	max_drawdown = np.min(drawdowns)

	wins = [p for p in profits if p > 0]
	winrate = len(wins) / len(trades) * 100
	avg_profit = np.mean(profits)
	sharpe = (np.mean(profits) / np.std(profits)) * np.sqrt(252) if np.std(profits) > 0 else 0

	return {
		"winrate": round(winrate, 2),
		"avg_profit": round(avg_profit, 4),
		"max_drawdown": round(max_drawdown, 4),  # классический equity drawdown
		"sharpe": round(sharpe, 2)
	}

# --- Сохранение сделок в БД ---
async def save_trades_to_db(trades, pair: str, strategy_name: str = "default", user_id: int = 1):
	async with get_session() as session:
		for t in trades:
			trade = TradeORM(
					symbol=pair,
					side=t.get("side", "buy"),
					amount=t.get("amount", 1.0),
					price=t["entry"],
					status=t["status"],
					leverage=t.get("leverage", 1.0),
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
	plt.figure(figsize=(12, 6))
	plt.plot(data["close"], label="Close Price", color="blue")

	for t in trades:
		# Находим ближайший индекс к цене входа
		entry_idx = int(np.argmin(np.abs(data["close"] - t["entry"])))
		plt.axvline(x=entry_idx, color="green", linestyle="--")
		plt.text(entry_idx, t["entry"], f"x{t.get('leverage',1)}",
					color="black", fontsize=8, rotation=90)

		# Находим ближайший индекс к цене выхода
		if "exit" in t:
			exit_idx = int(np.argmin(np.abs(data["close"] - t["exit"])))
			plt.axvline(x=exit_idx, color="red", linestyle="--")

	plt.title(f"Backtest {pair} — Mode: {settings.TRADING_MODE}")
	plt.xlabel("Time")
	plt.ylabel("Price")
	plt.legend()
	plt.show()


# --- Пример запуска ---
if __name__ == "__main__":
	loop = asyncio.get_event_loop()
	all_metrics = {}
	all_results = {}

	async def run_backtests():
		async with get_session() as session:
			strategies = await load_strategies(session)
			for pair in strategies.keys():
					df = pd.read_csv(f"data/{pair.replace('/', '')}_1h.csv")
					results = await backtest_strategy(df, pair, strategy_name="EMA+RSI", session=session)
					metrics = calculate_metrics(results)

					all_metrics[pair] = metrics
					all_results[pair] = results

					await save_trades_to_db(results, pair, strategy_name="EMA+RSI")
					await save_metrics_to_db(metrics, pair, strategy_name="EMA+RSI")

					plot_backtest(df, results, pair)

	loop.run_until_complete(run_backtests())

	df_report = pd.DataFrame.from_dict(all_metrics, orient="index")
	print("\n=== Сводный отчёт по всем парам ===")
	print(df_report)

	with pd.ExcelWriter("backtest_summary.xlsx", engine="openpyxl") as writer:
		df_report.to_excel(writer, sheet_name="Metrics")
		for pair, trades in all_results.items():
			df_trades = pd.DataFrame(trades)
			sheet_name = pair.replace("/", "_")[:30]
			df_trades.to_excel(writer, sheet_name=pair[:30])

	print("\nСводный отчёт сохранён в backtest_summary.xlsx (метрики + сделки)")
