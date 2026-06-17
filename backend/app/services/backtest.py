import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import asyncio
from datetime import datetime
from numba import njit
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import indicators, risk
from app.services.ml import MLService
from app.config import settings
from app.utils.logger import logger
from app.db.session import get_session
from app.services.exchange import load_strategies
from app.broker.rabbitmq import RabbitMQBroker
from app.db import crud
from app.models.trade import Trade

# --- ML Service ---
ml_service = MLService()
ml_service.load_model(path=settings.MODEL_PATH, model_type=settings.MODEL_TYPE)

broker = RabbitMQBroker()
asyncio.create_task(broker.connect())

def build_features(row: pd.Series) -> dict:
	"""Формируем полный набор признаков для ML модели из строки DataFrame."""
	return {
		"ema": row.get("ema_short", 0),
		"rsi": row.get("rsi", 50),
		"macd": row.get("macd_line", 0),
		"hour": pd.to_datetime(row.get("timestamp", datetime.utcnow())).hour,
		"atr": row.get("atr", 0),
		"bollinger_upper": row.get("boll_upper", 0),
		"bollinger_lower": row.get("boll_lower", 0),
		"bollinger": (row.get("close", 0) - row.get("boll_sma", 0)),
		"obv": row.get("obv", 0),
		"stochastic": row.get("stoch_k", 0),
		"vwap": row.get("vwap", 0),
		"ichimoku": row.get("ichimoku", 0),
		"volume": row.get("volume", 0),
		"volume_ma": row.get("vol_sma", 0),
		"news_sentiment": row.get("news_sentiment", 0),
		"last_price": row.get("last_price", 0),
		"spread": row.get("spread", 0),
		"liquidity_imbalance": row.get("liquidity_imbalance", 0),
		"mark_price": row.get("mark_price", 0)
	}

@njit
def fast_equity_curve(profits: np.ndarray, initial_deposit: float):
	equity_curve = np.cumsum(profits) + initial_deposit
	peak = np.maximum.accumulate(equity_curve)
	drawdowns = (equity_curve - peak) / peak
	return equity_curve, drawdowns

async def backtest_strategy(data: pd.DataFrame, pair: str, strategy: dict, session: AsyncSession = None):
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
		data["vol_sma"] = pd.Series(data["volume"]).rolling(window=strategy.get("volume_period", 20)).mean()

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

				# --- Проверка индикаторов ---
				for ind in condition:
					if ind == "EMA":
						if row["ema_short"] > row["ema_long"]:
							signals.append(True); direction = "long"
						elif row["ema_short"] < row["ema_long"] and market_type == "futures":
							signals.append(True); direction = "short"
						else:
							signals.append(False)

					elif ind == "RSI":
						rsi_lower = strategy.get("rsi_lower_threshold", 30)
						rsi_upper = strategy.get("rsi_upper_threshold", 70)
						if row["rsi"] < rsi_lower:
							signals.append(True); direction = "long"
						elif row["rsi"] > rsi_upper and market_type == "futures":
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
						stoch_lower = strategy.get("stochastic_lower_threshold", 20)
						stoch_upper = strategy.get("stochastic_upper_threshold", 80)
						if row["stoch_k"] < stoch_lower and row["stoch_k"] > row["stoch_d"]:
							signals.append(True); direction = "long"
						elif row["stoch_k"] > stoch_upper and row["stoch_k"] < row["stoch_d"] and market_type == "futures":
							signals.append(True); direction = "short"
						else:
							signals.append(False)

				# --- Фильтр по sentiment ---
				sentiment_long = strategy.get("sentiment_long_threshold", -0.5)
				sentiment_short = strategy.get("sentiment_short_threshold", 0.5)
				if row.get("news_sentiment", 0) < sentiment_long and direction == "long":
					signals.append(False)
				if row.get("news_sentiment", 0) > sentiment_short and direction == "short":
					signals.append(False)

				if all(signals):
					entry_price = row["close"]
					stop_price = risk.apply_stop_loss(entry_price, strategy["stop_loss"], direction)
					tp_levels = risk.apply_take_profit(entry_price, strategy["take_profit_targets"], direction)

					features = build_features(row)
					probability = ml_service.predict_signal(features)
					signal_strength = probability * settings.SIGNAL_STRENGTH_MULTIPLIER

					leverage = risk.calculate_leverage(pair, signal_strength)

					deposit = settings.DEFAULT_DEPOSIT
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
						"leverage": leverage,
						"news_sentiment": row.get("news_sentiment", 0)
					}

					logger.info(
						f"📈 Trade opened | {pair} | side={direction} | entry={entry_price} | stop={stop_price} | tp={tp_levels} "
						f"| amount={amount:.4f} | lev={leverage} | sentiment={row.get('news_sentiment', 0)}",
						extra=position
						)

					try:
						await broker.publish_telegram({
							"type": "trade",
							"trade": {
								"pair": pair,
								"side": direction,
								"entry": entry_price,
								"stop_loss": stop_price,
								"take_profit": tp_levels,
								"amount": amount,
								"leverage": leverage
							}
						})
					except Exception as e:
						logger.error(f"❌ Broker publish failed for {pair}: {e}")
					break

		elif position is not None:
			price = row["close"]
			if position["side"] == "long":
				if price <= position["stop"]:
					position["exit"] = price; position["status"] = "stopped"
					pnl = (price - position["entry"]) * position["amount"] * position["leverage"]
					logger.info(
						f"📉 Trade closed | {pair} | side=long | entry={position['entry']} | exit={price} "
						f"| status=stopped | pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
						extra=position
					)
					trades.append(position); position = None
				elif "ATR" in strategy["enabled_indicators"]:
					atr_value = row["atr"]
					dynamic_stop = position["entry"] - strategy.get("atr_multiplier", settings.ATR_MULTIPLIER) * atr_value
					if price <= dynamic_stop:
						position["exit"] = price; position["status"] = "atr_stop"
						pnl = (price - position["entry"]) * position["amount"] * position["leverage"]
						logger.info(
							f"📉 Trade closed | {pair} | side=long | entry={position['entry']} | exit={price} "
							f"| status=atr_stop | pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
							extra=position
						)
						trades.append(position); position = None
				elif price >= position["tp"][0]:
					position["exit"] = price; position["status"] = "take_profit"
					pnl = (price - position["entry"]) * position["amount"] * position["leverage"]
					logger.info(
						f"✅ Trade take_profit | {pair} | side=long | entry={position['entry']} | exit={price} "
						f"| pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
						extra=position
					)
					trades.append(position)
					position["tp"].pop(0)
					if len(position["tp"]) == 0: position = None

			elif position["side"] == "short":
				if price >= position["stop"]:
					position["exit"] = price; position["status"] = "stopped"
					pnl = (position["entry"] - price) * position["amount"] * position["leverage"]
					logger.info(
						f"📉 Trade closed | {pair} | side=short | entry={position['entry']} | exit={price} "
						f"| status=stopped | pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
						extra=position
					)
					trades.append(position); position = None
				elif "ATR" in strategy["enabled_indicators"]:
					atr_value = row["atr"]
					dynamic_stop = position["entry"] + strategy.get("atr_multiplier", settings.ATR_MULTIPLIER) * atr_value
					if price >= dynamic_stop:
						position["exit"] = price; position["status"] = "atr_stop"
						pnl = (position["entry"] - price) * position["amount"] * position["leverage"]
						logger.info(
							f"📉 Trade closed | {pair} | side=short | entry={position['entry']} | exit={price} "
							f"| status=atr_stop | pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
							extra=position
						)
						trades.append(position); position = None
				elif price <= position["tp"][0]:
					position["exit"] = price; position["status"] = "take_profit"
					pnl = (position["entry"] - price) * position["amount"] * position["leverage"]
					logger.info(
						f"✅ Trade take_profit | {pair} | side=short | entry={position['entry']} | exit={price} "
						f"| pnl={pnl:.4f} | sentiment={position.get('news_sentiment',0)}",
						extra=position
					)
					trades.append(position)
					position["tp"].pop(0)
					if len(position["tp"]) == 0: position = None
	return trades

# --- Метрики ---
def calculate_metrics(trades, initial_deposit=settings.DEFAULT_DEPOSIT):
	if not trades:
		return {"winrate": 0, "avg_profit": 0, "max_drawdown": 0, "sharpe": 0,
				"avg_sentiment_win": 0, "avg_sentiment_loss": 0}

	commission = settings.COMMISSION_RATE
	slippage = settings.SLIPPAGE_TOLERANCE

	profits = np.array([
		((t["exit"] - t["entry"]) - (t["entry"] * (commission + slippage)))
		* t.get("amount", 1.0) * t.get("leverage", 1)
		for t in trades if "exit" in t
	])

	equity_curve, drawdowns = fast_equity_curve(profits, initial_deposit)
	max_drawdown = np.min(drawdowns)

	wins = profits[profits > 0]
	winrate = len(wins) / len(trades) * 100 if len(trades) > 0 else 0
	avg_profit = np.mean(profits) if len(profits) > 0 else 0
	sharpe = (np.mean(profits) / np.std(profits)) * np.sqrt(252) if np.std(profits) > 0 else 0

	avg_sentiment_win = np.mean([t.get("news_sentiment", 0) for t in trades
									if "exit" in t and (t["exit"] - t["entry"]) > 0]) if wins.size > 0 else 0
	avg_sentiment_loss = np.mean([t.get("news_sentiment", 0) for t in trades
									if "exit" in t and (t["exit"] - t["entry"]) <= 0]) if len(trades) > len(wins) else 0

	metrics = {
		"winrate": round(winrate, 2),
		"avg_profit": round(avg_profit, 4),
		"max_drawdown": round(max_drawdown, 4),
		"sharpe": round(sharpe, 2),
		"avg_sentiment_win": round(avg_sentiment_win, 4),
		"avg_sentiment_loss": round(avg_sentiment_loss, 4)
	}

	# Логируем метрики для Prometheus/Grafana
	for key, value in metrics.items():
		logger.info("Metrics collected", extra={"metric": key, "value": value})

	return metrics

# --- Сохранение сделок и метрик ---
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
				profit_loss=((t.get("exit", 0) - t["entry"]) - (t["entry"] * (settings.COMMISSION_RATE + settings.SLIPPAGE_TOLERANCE)))
							* t.get("amount", 1.0) * t.get("leverage", 1) if "exit" in t else None,
				news_sentiment=t.get("news_sentiment", 0)
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
			"avg_sentiment_win": metrics["avg_sentiment_win"],
			"avg_sentiment_loss": metrics["avg_sentiment_loss"],
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
				# 🔹 Подмешиваем news_sentiment через MLService
				df = ml_service.prepare_data(df.to_dict("records"), symbol=pair.split("/")[0].lower())

				for strategy in strategy_list:
					strategy_name = strategy.get("name", "default")

					async def run_single_backtest(pair=pair, strategy=strategy, strategy_name=strategy_name, df=df.copy()):
						try:
							results = await backtest_strategy(df, pair, strategy, session=session)
							metrics = calculate_metrics(results, initial_deposit=settings.DEFAULT_DEPOSIT)

							all_metrics[f"{pair}_{strategy_name}"] = metrics
							all_results[f"{pair}_{strategy_name}"] = results

							await save_trades_to_db(results, pair, strategy_name=strategy_name)
							await save_metrics_to_db(metrics, pair, strategy_name=strategy_name)

							try:
								df_trades = pd.DataFrame(results)
								if not df_trades.empty:
									df_trades["result"] = (df_trades["exit"] - df_trades["entry"]).apply(lambda x: 1 if x > 0 else 0)
									train_metrics = ml_service.train(df_trades, model_type=settings.MODEL_TYPE)
									ml_service.save_model(settings.MODEL_PATH)
									logger.info(f"ML обучение завершено для {pair} ({strategy_name}): {train_metrics}")
							except Exception as e:
								logger.error(f"❌ Ошибка обучения ML на истории {pair} ({strategy_name}): {e}")
								await crud.create_risk_log(session, {
									"reason": f"ML training failed: {e}",
									"symbol": pair,
									"position_size": None,
									"deposit": settings.DEFAULT_DEPOSIT,
									"sentiment": None,
									"profit_loss": None,
									"expected_pnl": None
								})

							plot_backtest(df, results, pair, strategy_name)

						except Exception as e:
							logger.error(f"❌ Ошибка бэктеста для {pair} ({strategy_name}): {e}")
							await crud.create_risk_log(session, {
								"reason": f"Backtest failed: {e}",
								"symbol": pair,
								"position_size": None,
								"deposit": settings.DEFAULT_DEPOSIT,
								"sentiment": None,
								"profit_loss": None,
								"expected_pnl": None
							})

					tasks.append(run_single_backtest())

			await asyncio.gather(*tasks)

	loop.run_until_complete(run_backtests())

	df_report = pd.DataFrame.from_dict(all_metrics, orient="index")
	print("\n=== Сводный отчёт по всем парам и стратегиям ===")
	print(df_report)

	# 🔹 Excel отчёт только для отладки
	if getattr(settings, "DEBUG_EXPORT", False):
		from app.utils.export import export_to_excel
		export_to_excel(all_metrics, all_results)
		print("\nСводный отчёт сохранён в backtest_summary.xlsx (метрики + сделки)")

