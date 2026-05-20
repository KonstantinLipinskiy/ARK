from celery import Celery
from app.config import settings

celery_app = Celery(
	"ark_bot",
	broker=settings.CELERY_BROKER_URL,
	backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.beat_schedule = {
	# --- OHLCV ---
	"update-ohlcv-hourly": {
		"task": "app.tasks.update_ohlcv_task",
		"schedule": 3600.0,  # каждый час
		"args": ["1h"]
	},
	"update-ohlcv-daily": {
		"task": "app.tasks.update_ohlcv_task",
		"schedule": 86400.0,  # раз в сутки
		"args": ["1d"]
	},

	# --- Funding Rate ---
	"update-funding-rate-btc": {
		"task": "app.tasks.update_funding_rate_task",
		"schedule": 28800.0,  # каждые 8 часов (биржи обновляют funding rate)
		"args": ["BTC/USDT"]
	},
	"update-funding-rate-eth": {
		"task": "app.tasks.update_funding_rate_task",
		"schedule": 28800.0,
		"args": ["ETH/USDT"]
	},

	# --- Мониторинг тикеров ---
	"monitor-ticker-btc": {
		"task": "app.tasks.monitor_ticker_task",
		"schedule": 600.0,  # каждые 10 минут
		"args": ["BTC/USDT"]
	},
	"monitor-ticker-eth": {
		"task": "app.tasks.monitor_ticker_task",
		"schedule": 600.0,
		"args": ["ETH/USDT"]
	},

	# --- Мониторинг стакана ---
	"monitor-order-book-btc": {
		"task": "app.tasks.monitor_order_book_task",
		"schedule": 900.0,  # каждые 15 минут
		"args": ["BTC/USDT"]
	},
	"monitor-order-book-eth": {
		"task": "app.tasks.monitor_order_book_task",
		"schedule": 900.0,
		"args": ["ETH/USDT"]
	},
}

celery_app.conf.timezone = "UTC"
