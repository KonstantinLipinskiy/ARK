import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import asyncio
from datetime import datetime
from numba import njit
from app.services import indicators, risk
from app.services.ml import MLService
from app.config import settings
from app.utils.logger import logger
from app.db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.strategy_service import load_strategies
from app.broker.rabbitmq import RabbitMQBroker
from app.db import crud
from app.models.trade import Trade

# --- ML Service ---
ml_service = MLService()
ml_service.load_model("models/sklearn_model.pkl", model_type="sklearn")

broker = RabbitMQBroker()

def build_features(row: pd.Series) -> dict:
	"""Формируем признаки для ML модели из строки DataFrame."""
	return {
		"ema": row.get("ema_short", 0),
		"rsi": row.get("rsi", 50),
		"macd": row.get("macd_line", 0),
		"hour": datetime.utcnow().hour,
		"atr": row.get("atr", 0)
	}

# --- Оптимизация индикаторов через numba ---
@njit
def fast_equity_curve(profits: np.ndarray, initial_deposit: float):
	equity_curve = np.cumsum(profits) + initial_deposit
	peak = np.maximum.accumulate(equity_curve)
	drawdowns = (equity_curve - peak) / peak
	return equity_curve, drawdowns

# --- Основной бэктест ---
async def backtest_strategy(data: pd.DataFrame, pair: str, strategy: dict, session: AsyncSession = None):
	"""Прогон одной стратегии для пары"""
	trades = []
	position = None
	market_type = settings.TRADING_MODE

	# --- Индикаторы ---
	if "EMA" in strategy["enabled_indicators"]:
		data["ema_short"] = indicators.ema(pd.Series(data["close"]), strategy["ema_short"])
		data["ema_long"] = indicators.ema(pd.Series(data["close"]), strategy["ema_long"])

	if "RSI" in strategy["enabled_indicators"]:
		data["rsi"] = indicators.rsi(pd.Series(data["close"]), strategy["rsi_period"])

	if "MACD" in strategy["enabled_indicators"]:
		macd_line, signal_line = indicators.macd(pd.Series(data["close"]),
																strategy["macd_fast"],
																strategy["macd_slow"],
																strategy["macd_signal"])
		data["macd_line"], data["macd_signal"] = macd_line, signal_line

	if "Bollinger" in strategy["enabled_indicators"]:
		upper, sma, lower = indicators.bollinger(pd.Series(data["close"]), strategy["bollinger_period"])
		data["boll_upper"], data["boll_sma"], data["boll_lower"] = upper, sma, lower

	if "ATR" in strategy["enabled_indicators"]:
		data["atr"] = indicators.atr(pd.Series(data["high"]),
												pd.Series(data["low"]),
												pd.Series(data["close"]),
												strategy["atr_period"])

	if "OBV" in strategy["enabled_indicators"]:
		data["obv"] = indicators.obv(pd.Series(data["close"]), pd.Series(data["volume"]))

	if "Stochastic" in strategy["enabled_indicators"]:
		data["stoch_k"] = indicators.stochastic(pd.Series(data["close"]),
															pd.Series(data["high"]),
															pd.Series(data["low"]),
															strategy["stochastic_period"])
		data["stoch_d"] = pd.Series(data["stoch_k"]).rolling(window=3).mean()

	if "Volume" in strategy["enabled_indicators"]:
		data["vol_sma"] = pd.Series(data["volume"]).rolling(window=20).mean()

	# --- Основной цикл по свечам ---
	for i in range(1, len(data)):
		row = data.iloc[i]

		if "OBV" in strategy["enabled_indicators"] and row["obv"] <= data["obv"].iloc[i-1]:
			continue
		if "Volume" in strategy["enabled_indicators"] and row["volume"] < row["vol_sma"]:
			continue

		if position is None and "entry_conditions" in strategy:
			for condition in strategy["entry_conditions"]:
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
						stop_price = risk.apply_stop_loss(entry_price, strategy["stop_loss"], direction)
						tp_levels = risk.apply_take_profit(entry_price, strategy["take_profit_targets"], direction)

						features = build_features(row)
						probability = ml_service.predict_signal(features)
						signal_strength = probability * 2

						leverage = risk.calculate_leverage(pair, signal_strength)

						deposit = 1000
						amount = await risk.calculate_position_size(
							symbol=pair,
							deposit=deposit,
							entry_price=entry_price,
							stop_loss_pct=strategy["stop_loss"],
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
					elif "ATR" in strategy["enabled_indicators"]:
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
					elif "ATR" in strategy["enabled_indicators"]:
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

	profits = np.array([
		(t["exit"] - t["entry"]) * t.get("amount", 1.0) * t.get("leverage", 1)
		for t in trades if "exit" in t
	])

	equity_curve, drawdowns = fast_equity_curve(profits, initial_deposit)
	max_drawdown = np.min(drawdowns)

	wins = profits[profits > 0]
	winrate = len(wins) / len(trades) * 100 if len(trades) > 0 else 0
	avg_profit = np.mean(profits) if len(profits) > 0 else 0
	sharpe = (np.mean(profits) / np.std(profits)) * np.sqrt(252) if np.std(profits) > 0 else 0

	return {
		"winrate": round(winrate, 2),
		"avg_profit": round(avg_profit, 4),
		"max_drawdown": round(max_drawdown, 4),
		"sharpe": round(sharpe, 2)
	}

# --- Сохранение сделок и метрик через CRUD ---
async def save_trades_to_db(trades, pair: str, strategy_name: str = "default", user_id: int = 1):
	async with get_session() as session:
		for t in trades:
			trade_model = Trade(
					symbol=pair,
					side=t.get("side", "buy"),
					amount=t.get("amount", 1.0),
					price=t["entry"],
					status=t["status"],
					leverage=t.get("leverage", 1.0),
					user_id=user_id,
					entry_price=t["entry"],
					exit_price=t.get("exit"),
					profit_loss=(t.get("exit", 0) - t["entry"]) * t.get("amount", 1.0) * t.get("leverage", 1)
						if "exit" in t else None
			)
			await crud.create_trade(session, trade_model)

async def save_metrics_to_db(metrics: dict, pair: str, strategy_name: str = "default", user_id: int = 1):
	async with get_session() as session:
		report_data = {
			"symbol": pair,
			"strategy": strategy_name,
			"winrate": metrics["winrate"],
			"avg_profit": metrics["avg_profit"],
			"max_drawdown": metrics["max_drawdown"],
			"sharpe": metrics["sharpe"],
			"user_id": user_id
		}
		await crud.create_backtest_report(session, report_data)

# --- Визуализация ---
def plot_backtest(data: pd.DataFrame, trades: list, pair: str, strategy_name: str):
	plt.figure(figsize=(14, 7))
	plt.plot(data["close"], label="Close Price", color="blue")

	if "ema_short" in data.columns:
		plt.plot(data["ema_short"], label="EMA Short", color="orange")
	if "ema_long" in data.columns:
		plt.plot(data["ema_long"], label="EMA Long", color="red")
	if "rsi" in data.columns:
		plt.plot(data["rsi"], label="RSI", color="purple")
	if "macd_line" in data.columns and "macd_signal" in data.columns:
		plt.plot(data["macd_line"], label="MACD Line", color="green")
		plt.plot(data["macd_signal"], label="MACD Signal", color="brown")
	if "boll_upper" in data.columns and "boll_lower" in data.columns:
		plt.plot(data["boll_upper"], label="Bollinger Upper", linestyle="--", color="grey")
		plt.plot(data["boll_lower"], label="Bollinger Lower", linestyle="--", color="grey")

	for t in trades:
		entry_idx = int(np.argmin(np.abs(data["close"].values - t["entry"])))
		plt.axvline(x=entry_idx, color="green", linestyle="--")
		plt.text(entry_idx, t["entry"], f"x{t.get('leverage',1)}",
					color="black", fontsize=8, rotation=90)

		if "exit" in t:
			exit_idx = int(np.argmin(np.abs(data["close"].values - t["exit"])))
			plt.axvline(x=exit_idx, color="red", linestyle="--")

	plt.title(f"Backtest {pair} — {strategy_name} — Mode: {settings.TRADING_MODE}")
	plt.xlabel("Time")
	plt.ylabel("Price / Indicators")
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
			tasks = []

			for pair, strategy_list in strategies.items():
					df = pd.read_csv(f"data/{pair.replace('/', '')}_1h.csv")

					for strategy in strategy_list:
						strategy_name = strategy.get("name", "default")

						async def run_single_backtest(pair=pair, strategy=strategy, strategy_name=strategy_name, df=df.copy()):
							results = await backtest_strategy(df, pair, strategy, session=session)
							metrics = calculate_metrics(results)

							all_metrics[f"{pair}_{strategy_name}"] = metrics
							all_results[f"{pair}_{strategy_name}"] = results

							await save_trades_to_db(results, pair, strategy_name=strategy_name)
							await save_metrics_to_db(metrics, pair, strategy_name=strategy_name)

							# --- Автоматическое обучение ML модели на истории ---
							try:
									df_trades = pd.DataFrame(results)
									if not df_trades.empty:
										df_trades["result"] = (df_trades["exit"] - df_trades["entry"]).apply(lambda x: 1 if x > 0 else 0)
										train_metrics = ml_service.train(df_trades, model_type="sklearn")
										logger.info(f"ML обучение завершено для {pair} ({strategy_name}): {train_metrics}")
							except Exception as e:
									logger.error(f"Ошибка обучения ML на истории {pair} ({strategy_name}): {e}")

							plot_backtest(df, results, pair, strategy_name)

						tasks.append(run_single_backtest())

			# 🔹 Запускаем все бэктесты параллельно
			await asyncio.gather(*tasks)

	loop.run_until_complete(run_backtests())

	df_report = pd.DataFrame.from_dict(all_metrics, orient="index")
	print("\n=== Сводный отчёт по всем парам и стратегиям ===")
	print(df_report)

	with pd.ExcelWriter("backtest_summary.xlsx", engine="openpyxl") as writer:
		df_report.to_excel(writer, sheet_name="Metrics")
		for key, trades in all_results.items():
			df_trades = pd.DataFrame(trades)
			sheet_name = key.replace("/", "_")[:30]
			df_trades.to_excel(writer, sheet_name=sheet_name)

	print("\nСводный отчёт сохранён в backtest_summary.xlsx (метрики + сделки)")

