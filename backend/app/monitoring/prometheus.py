# app/monitoring/prometheus.py
from fastapi import APIRouter, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from prometheus_client import Gauge, Counter, Histogram, generate_latest
from app.db.session import get_db
from app.db.schemas import TradeORM, SignalORM
from app.utils.metrics import calculate_metrics, ml_accuracy, ml_loss
from app.broker.rabbitmq import RabbitMQBroker
from app.cache.redis import RedisCache

router = APIRouter()

# 🔹 Метрики Prometheus (торговля)
winrate_gauge = Gauge("bot_winrate", "Winrate of trades")
profit_gauge = Gauge("bot_total_profit", "Total profit of trades")
drawdown_gauge = Gauge("bot_max_drawdown", "Maximum drawdown")
trades_counter = Gauge("bot_trades_count", "Number of trades executed")
sharpe_gauge = Gauge("bot_sharpe_ratio", "Sharpe ratio of trades")
sortino_gauge = Gauge("bot_sortino_ratio", "Sortino ratio of trades")
profit_factor_gauge = Gauge("bot_profit_factor", "Profit factor of trades")
errors_counter = Counter("bot_errors_total", "Number of failed orders")
active_signals_gauge = Gauge("bot_active_signals", "Number of active signals")

# 🔹 Метрики Prometheus (RabbitMQ)
rabbitmq_messages_published = Counter("rabbitmq_messages_published_total", "Total messages published to RabbitMQ")
rabbitmq_messages_consumed = Counter("rabbitmq_messages_consumed_total", "Total messages consumed from RabbitMQ")
rabbitmq_errors_total = Counter("rabbitmq_errors_total", "Total RabbitMQ errors")
rabbitmq_processing_time = Histogram("rabbitmq_processing_time_seconds", "Message processing time in RabbitMQ")

# 🔹 Метрики Prometheus (Redis)
redis_keys_total = Gauge("redis_keys_total", "Total number of keys in Redis")
redis_latency_seconds = Histogram("redis_latency_seconds", "Redis latency in seconds")

# 🔹 Эндпоинт /metrics
@router.get("/metrics")
async def metrics_endpoint(db: AsyncSession = Depends(get_db)) -> Response:
	# --- Метрики торговли ---
	result = await db.execute(select(TradeORM))
	trades = result.scalars().all()

	stats = calculate_metrics(trades)

	winrate_gauge.set(stats["winrate"])
	profit_gauge.set(stats["total_profit"])
	drawdown_gauge.set(stats["max_drawdown"])
	trades_counter.set(stats["trades_count"])
	sharpe_gauge.set(stats["sharpe_ratio"])
	sortino_gauge.set(stats["sortino_ratio"])
	profit_factor_gauge.set(stats["profit_factor"])

	# Количество активных сигналов
	active_signals = await db.scalar(
		select(func.count()).select_from(SignalORM).filter(SignalORM.status == "active")
	)
	active_signals_gauge.set(active_signals or 0)

	# --- Метрики ML обучения ---
	# ml_accuracy и ml_loss обновляются при обучении через utils/metrics.py
	# Здесь они просто публикуются в Prometheus

	# --- Метрики RabbitMQ ---
	broker = RabbitMQBroker()
	try:
		metrics = broker.get_metrics()
		rabbitmq_messages_published.inc(metrics["messages_published"])
		rabbitmq_messages_consumed.inc(metrics["messages_consumed"])
		rabbitmq_errors_total.inc(metrics["errors_total"])
		rabbitmq_processing_time.observe(metrics["avg_processing_time"])
	except Exception:
		rabbitmq_errors_total.inc()

	# --- Метрики Redis ---
	redis = RedisCache()
	try:
		keys = await redis.keys("*")
		redis_keys_total.set(len(keys))

		import time
		start = time.time()
		pong = await redis.health_check()
		elapsed = round(time.time() - start, 3)
		if pong:
			redis_latency_seconds.observe(elapsed)
	except Exception:
		# Если Redis недоступен, просто логируем ошибку
		redis_keys_total.set(0)

	return Response(generate_latest(), media_type="text/plain")

# 🔹 Логирование ошибок
def log_error():
	errors_counter.inc()
	rabbitmq_errors_total.inc()
