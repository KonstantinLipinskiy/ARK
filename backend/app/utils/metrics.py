# app/utils/metrics.py
from typing import List, Dict, Union, Optional
import math
import asyncio
import numpy as np
from prometheus_client import Gauge, Counter, Histogram
from app.utils.logger import logger, metrics_logger

# --- Trading Metrics ---
def _extract_profit(trade: Union[Dict, object]) -> float:
	"""Универсальный доступ к профиту (dict или ORM)."""
	try:
		return trade["profit"] if isinstance(trade, dict) else getattr(trade, "profit", 0.0)
	except Exception as e:
		logger.error(f"Ошибка извлечения профита: {e}", extra={"operation": "metrics", "collection": "trading"})
		return 0.0

def calculate_profit(trades: List[Union[Dict, object]]) -> float:
	return sum(_extract_profit(trade) for trade in trades)

def calculate_winrate(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	wins = sum(1 for trade in trades if _extract_profit(trade) > 0)
	return wins / len(trades)

def calculate_average_profit(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	return calculate_profit(trades) / len(trades)

def calculate_max_drawdown(trades: List[Union[Dict, object]]) -> float:
	equity = 0.0
	max_equity = 0.0
	max_drawdown = 0.0
	for trade in trades:
		equity += _extract_profit(trade)
		max_equity = max(max_equity, equity)
		drawdown = max_equity - equity
		max_drawdown = max(max_drawdown, drawdown)
	return max_drawdown

def calculate_sharpe_ratio(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	try:
		profits = np.array([_extract_profit(t) for t in trades])
		avg = np.mean(profits)
		std = np.std(profits)
		return avg / std if std > 0 else 0.0
	except Exception as e:
		logger.error(f"Ошибка расчёта Sharpe: {e}", extra={"operation": "metrics", "collection": "trading"})
		return 0.0

def calculate_sortino_ratio(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	try:
		profits = np.array([_extract_profit(t) for t in trades])
		avg = np.mean(profits)
		downside = profits[profits < 0]
		if len(downside) == 0:
			return float("inf")
		std_down = np.std(downside)
		return avg / std_down if std_down > 0 else 0.0
	except Exception as e:
		logger.error(f"Ошибка расчёта Sortino: {e}", extra={"operation": "metrics", "collection": "trading"})
		return 0.0

def calculate_profit_factor(trades: List[Union[Dict, object]]) -> float:
	try:
		gains = sum(_extract_profit(t) for t in trades if _extract_profit(t) > 0)
		losses = abs(sum(_extract_profit(t) for t in trades if _extract_profit(t) < 0))
		return gains / losses if losses > 0 else float("inf")
	except Exception as e:
		logger.error(f"Ошибка расчёта Profit Factor: {e}", extra={"operation": "metrics", "collection": "trading"})
		return 0.0

def calculate_max_consecutive(trades: List[Union[Dict, object]]) -> Dict[str, int]:
	max_wins = max_losses = 0
	current_wins = current_losses = 0
	for trade in trades:
		if _extract_profit(trade) > 0:
			current_wins += 1
			max_wins = max(max_wins, current_wins)
			current_losses = 0
		else:
			current_losses += 1
			max_losses = max(max_losses, current_losses)
			current_wins = 0
	return {"max_consecutive_wins": max_wins, "max_consecutive_losses": max_losses}

def calculate_metrics(trades: List[Union[Dict, object]]) -> Dict:
	cancelled = sum(1 for t in trades if getattr(t, "status", None) == "cancelled" or
					(isinstance(t, dict) and t.get("status") == "cancelled"))

	return {
		"total_profit": calculate_profit(trades),
		"winrate": calculate_winrate(trades),
		"average_profit": calculate_average_profit(trades),
		"max_drawdown": calculate_max_drawdown(trades),
		"sharpe_ratio": calculate_sharpe_ratio(trades),
		"sortino_ratio": calculate_sortino_ratio(trades),
		"profit_factor": calculate_profit_factor(trades),
		**calculate_max_consecutive(trades),
		"trades_count": len(trades),
		"cancelled_trades": cancelled
	}

# --- Метрики по пользователям и стратегиям ---
def calculate_metrics_by_user(trades: List[Union[Dict, object]], user_id: str) -> Dict:
	user_trades = [t for t in trades if getattr(t, "user_id", None) == user_id or (isinstance(t, dict) and t.get("user_id") == user_id)]
	return calculate_metrics(user_trades)

def calculate_metrics_by_strategy(trades: List[Union[Dict, object]], strategy: str) -> Dict:
	strategy_trades = [t for t in trades if getattr(t, "strategy", None) == strategy or (isinstance(t, dict) and t.get("strategy") == strategy)]
	return calculate_metrics(strategy_trades)

# --- Асинхронный расчёт ---
async def calculate_metrics_async(trades: List[Union[Dict, object]]) -> Dict:
	loop = asyncio.get_event_loop()
	return await loop.run_in_executor(None, lambda: calculate_metrics(trades))

# --- ML Training Metrics (Prometheus) ---
ml_accuracy = Gauge("ml_training_accuracy", "Accuracy of ML training")
ml_loss = Gauge("ml_training_loss", "Loss of ML training")
ml_precision = Gauge("ml_training_precision", "Precision of ML training")
ml_recall = Gauge("ml_training_recall", "Recall of ML training")

def get_accuracy() -> float:
	try:
		return ml_accuracy._value.get() or 0.0
	except Exception as e:
		metrics_logger.error(f"Ошибка получения accuracy: {e}", extra={"metric": "accuracy", "value": None, "symbol": None})
		return 0.0

def get_loss() -> float:
	try:
		return ml_loss._value.get() or 0.0
	except Exception as e:
		metrics_logger.error(f"Ошибка получения loss: {e}", extra={"metric": "loss", "value": None, "symbol": None})
		return 0.0

def get_precision() -> float:
	try:
		return ml_precision._value.get() or 0.0
	except Exception as e:
		metrics_logger.error(f"Ошибка получения precision: {e}", extra={"metric": "precision", "value": None, "symbol": None})
		return 0.0

def get_recall() -> float:
	try:
		return ml_recall._value.get() or 0.0
	except Exception as e:
		metrics_logger.error(f"Ошибка получения recall: {e}", extra={"metric": "recall", "value": None, "symbol": None})
		return 0.0

# --- Agent Metrics (Prometheus) ---
AGENT_REQUESTS = Counter("agent_requests_total", "Количество запросов к агентам")
AGENT_ERRORS = Counter("agent_errors_total", "Количество ошибок агентов")
AGENT_LATENCY = Histogram("agent_latency_seconds", "Время ответа агентов")

# --- Report Metrics (Prometheus) ---
REPORT_SEARCH_ACCURACY = Gauge("report_search_accuracy", "Точность поиска документов для отчётов (% релевантных)")
REPORT_LATENCY_HISTOGRAM = Histogram("report_latency_seconds", "Распределение времени ответа отчётов")

# 🔹 Добавляем недостающие метрики для ReportsWorker
REPORT_REQUESTS_TOTAL = Counter("report_requests_total", "Количество запросов на генерацию отчётов")
REPORT_AVG_RESPONSE_TIME = Gauge("report_avg_response_time_seconds", "Среднее время ответа отчётов")

def export_report_metrics(search_accuracy: float, latency: float):
	try:
		REPORT_SEARCH_ACCURACY.set(search_accuracy)
		REPORT_LATENCY_HISTOGRAM.observe(latency)
		metrics_logger.info(
			f"Экспорт метрик отчётов: accuracy={search_accuracy}, latency={latency}",
			extra={"metric": "report_search_accuracy", "value": search_accuracy, "symbol": None}
		)
	except Exception as e:
		metrics_logger.error(
			f"Ошибка экспорта метрик отчётов: {e}",
			extra={"metric": "report_search_accuracy", "value": None, "symbol": None}
		)

# --- ML Training Extended Metrics ---
ml_epoch_loss = Histogram("ml_training_epoch_loss", "Loss per epoch during ML training")
ml_training_time = Gauge("ml_training_time_seconds", "Total training time in seconds")
ml_learning_rate = Gauge("ml_training_learning_rate", "Learning rate used in training")

def export_ml_metrics(metrics: Dict[str, float], epoch_losses: Optional[List[float]] = None,
						training_time: Optional[float] = None, learning_rate: Optional[float] = None):
	try:
		if "accuracy" in metrics and metrics["accuracy"] is not None:
			ml_accuracy.set(metrics["accuracy"])
		if "loss" in metrics and metrics["loss"] is not None:
			ml_loss.set(metrics["loss"])
		if "precision" in metrics and metrics["precision"] is not None:
			ml_precision.set(metrics["precision"])
		if "recall" in metrics and metrics["recall"] is not None:
			ml_recall.set(metrics["recall"])

		if epoch_losses:
			for l in epoch_losses:
				ml_epoch_loss.observe(l)
		if training_time is not None:
			ml_training_time.set(training_time)
		if learning_rate is not None:
			ml_learning_rate.set(learning_rate)

		metrics_logger.info(
			f"Экспорт ML метрик: {metrics}, training_time={training_time}, lr={learning_rate}",
			extra={"metric": "ml_training", "value": metrics.get("accuracy"), "symbol": None}
		)
	except Exception as e:
		metrics_logger.error(
			f"Ошибка экспорта ML метрик: {e}",
			extra={"metric": "ml_training", "value": None, "symbol": None}
		)

# --- ML Cross-Validation Metrics (Prometheus) ---
ml_cv_accuracy = Gauge("ml_cv_accuracy", "Average accuracy across CV folds")
ml_cv_precision = Gauge("ml_cv_precision", "Average precision across CV folds")
ml_cv_recall = Gauge("ml_cv_recall", "Average recall across CV folds")
ml_cv_loss = Gauge("ml_cv_loss", "Average loss across CV folds")

def aggregate_cv_metrics(list_of_metrics: List[Dict[str, float]]) -> Dict[str, float]:
	"""
	Усреднение метрик accuracy, precision, recall, loss по фолдам.
	list_of_metrics: список словарей вида {"accuracy": ..., "precision": ..., "recall": ..., "loss": ...}
	"""
	if not list_of_metrics:
		return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "loss": 0.0}

	acc = [m.get("accuracy", 0.0) for m in list_of_metrics]
	prec = [m.get("precision", 0.0) for m in list_of_metrics]
	rec = [m.get("recall", 0.0) for m in list_of_metrics]
	loss = [m.get("loss", 0.0) for m in list_of_metrics]

	return {
		"accuracy": float(np.mean(acc)),
		"precision": float(np.mean(prec)),
		"recall": float(np.mean(rec)),
		"loss": float(np.mean(loss))
	}

def export_cv_metrics(metrics: Dict[str, float]):
	"""Экспорт усреднённых метрик кросс-валидации в Prometheus."""
	try:
		if "accuracy" in metrics and metrics["accuracy"] is not None:
			ml_cv_accuracy.set(metrics["accuracy"])
		if "precision" in metrics and metrics["precision"] is not None:
			ml_cv_precision.set(metrics["precision"])
		if "recall" in metrics and metrics["recall"] is not None:
			ml_cv_recall.set(metrics["recall"])
		if "loss" in metrics and metrics["loss"] is not None:
			ml_cv_loss.set(metrics["loss"])

		metrics_logger.info(
			f"Экспорт CV метрик: {metrics}",
			extra={"metric": "ml_cv", "value": metrics.get("accuracy"), "symbol": None}
		)
	except Exception as e:
		metrics_logger.error(
			f"Ошибка экспорта CV метрик: {e}",
			extra={"metric": "ml_cv", "value": None, "symbol": None}
		)

# --- Auto Logging Metrics (Prometheus) ---
ml_training_runs_total = Counter("ml_training_runs_total", "Количество запусков обучения ML моделей")
ml_predictions_total = Counter("ml_predictions_total", "Количество предсказаний ML моделей")
ml_prediction_confidence = Histogram("ml_prediction_confidence", "Распределение confidence score предсказаний")

# 🔹 Новые метрики для latency и ошибок
ml_prediction_latency = Histogram("ml_prediction_latency_seconds", "Latency of ML predictions")
ml_errors_total = Counter("ml_errors_total", "Количество ошибок ML обучения/предсказаний")

def log_training_run(metrics: Dict[str, float], epoch_losses: Optional[List[float]] = None,
						training_time: Optional[float] = None, learning_rate: Optional[float] = None):
	"""Логирование запуска обучения модели."""
	try:
		ml_training_runs_total.inc()
		if "accuracy" in metrics and metrics["accuracy"] is not None:
			ml_accuracy.set(metrics["accuracy"])
		if "loss" in metrics and metrics["loss"] is not None:
			ml_loss.set(metrics["loss"])
		if training_time is not None:
			ml_training_time.set(training_time)
		if learning_rate is not None:
			ml_learning_rate.set(learning_rate)

		metrics_logger.info(
			f"Логирование обучения: {metrics}, training_time={training_time}, lr={learning_rate}",
			extra={"metric": "ml_training_run", "value": metrics.get("accuracy"), "symbol": None}
		)
	except Exception as e:
		ml_errors_total.inc()
		metrics_logger.error(
			f"Ошибка логирования обучения: {e}",
			extra={"metric": "ml_training_run", "value": None, "symbol": None}
		)

def log_prediction(features: Dict[str, float], result: Dict[str, float], confidence: float, latency: Optional[float] = None):
	"""
	Логирование предсказания модели.
	features: входные признаки
	result: словарь с результатами предсказания (например, success_probability)
	confidence: confidence score
	latency: время выполнения предсказания (секунды)
	"""
	try:
		ml_predictions_total.inc()
		ml_prediction_confidence.observe(confidence)
		if latency is not None:
			ml_prediction_latency.observe(latency)

		metrics_logger.info(
			f"Логирование предсказания: confidence={confidence}, latency={latency}, result={result}",
			extra={"metric": "ml_prediction", "value": confidence, "symbol": None}
		)
	except Exception as e:
		ml_errors_total.inc()
		metrics_logger.error(
			f"Ошибка логирования предсказания: {e}",
			extra={"metric": "ml_prediction", "value": None, "symbol": None}
		)
