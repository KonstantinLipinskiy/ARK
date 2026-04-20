from prometheus_client import Gauge, Counter, Histogram, generate_latest
from fastapi import APIRouter, Response
from app.utils.metrics import calculate_metrics

router = APIRouter()

# Метрики Prometheus
winrate_gauge = Gauge("bot_winrate", "Winrate of trades")
profit_gauge = Gauge("bot_total_profit", "Total profit of trades")
drawdown_gauge = Gauge("bot_max_drawdown", "Maximum drawdown")
trades_counter = Counter("bot_trades_count", "Number of trades executed")

# Эндпоинт /metrics
@router.get("/metrics")
def metrics_endpoint() -> Response:
	# Здесь мы берём список сделок из БД или сервиса
	trades = [
		{"profit": 50},
		{"profit": -20},
		{"profit": 30},
	]

	stats = calculate_metrics(trades)

	# Обновляем метрики
	winrate_gauge.set(stats["winrate"])
	profit_gauge.set(stats["total_profit"])
	drawdown_gauge.set(stats["max_drawdown"])
	trades_counter.inc(stats["trades_count"])

	return Response(generate_latest(), media_type="text/plain")
