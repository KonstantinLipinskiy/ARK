# app/monitoring/prometheus.py
from fastapi import APIRouter, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from prometheus_client import Gauge, Counter, generate_latest
from app.db.session import get_db
from app.db.schemas import TradeORM, SignalORM
from app.utils.metrics import calculate_metrics, ml_accuracy, ml_loss

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

# 🔹 Эндпоинт /metrics
@router.get("/metrics")
async def metrics_endpoint(db: AsyncSession = Depends(get_db)) -> Response:
	# Берём реальные сделки из БД
	result = await db.execute(select(TradeORM))
	trades = result.scalars().all()

	stats = calculate_metrics(trades)

	# Обновляем метрики торговли
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

	# 🔹 Метрики ML обучения (пример: последние значения)
	# Эти значения обновляются через export_ml_metrics() в utils/metrics.py
	# Здесь мы просто публикуем их в Prometheus
	# ml_accuracy и ml_loss уже являются Gauge и обновляются при обучении

	return Response(generate_latest(), media_type="text/plain")

# 🔹 Логирование ошибок
def log_error():
	errors_counter.inc()
