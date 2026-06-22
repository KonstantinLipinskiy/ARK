# app/celery_app.py
from celery import Celery
from celery.schedules import crontab
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

	# --- CSV обновление раз в неделю ---
	"update-csv-weekly": {
		"task": "app.tasks.update_csv_task",
		"schedule": crontab(hour=2, minute=0, day_of_week="sun"),  # каждое воскресенье в 02:00
		"args": [settings.DEFAULT_TIMEFRAME, settings.DEFAULT_DAYS, settings.DATA_DIR]
	},

	# --- Backtest запуск раз в неделю ---
	"run-backtest-weekly": {
		"task": "app.tasks.run_backtest_task",
		"schedule": crontab(hour=3, minute=0, day_of_week="sun"),  # каждое воскресенье в 03:00
		"args": []
	},
}

# --- Funding Rate ---
for pair in settings.PAIRS:
	name = pair.split("/")[0].lower()
	celery_app.conf.beat_schedule[f"update-funding-rate-{name}"] = {
		"task": "app.tasks.update_funding_rate_task",
		"schedule": 28800.0,  # каждые 8 часов
		"args": [pair]
	}

# --- Мониторинг тикеров ---
for pair in settings.PAIRS:
	name = pair.split("/")[0].lower()
	celery_app.conf.beat_schedule[f"monitor-ticker-{name}"] = {
		"task": "app.tasks.monitor_ticker_task",
		"schedule": 600.0,  # каждые 10 минут
		"args": [pair]
	}

# --- Мониторинг стакана ---
for pair in settings.PAIRS:
	name = pair.split("/")[0].lower()
	celery_app.conf.beat_schedule[f"monitor-order-book-{name}"] = {
		"task": "app.tasks.monitor_order_book_task",
		"schedule": 900.0,  # каждые 15 минут
		"args": [pair]
	}

# --- Новости ---
for pair in settings.PAIRS:
	name = pair.split("/")[0].lower()
	celery_app.conf.beat_schedule[f"fetch-news-{name}-hourly"] = {
		"task": "app.tasks.fetch_crypto_news_task",
		"schedule": 3600.0,  # каждый час
		"args": [pair]  # теперь передаём полную пару, например "BTC/USDT"
	}

celery_app.conf.timezone = "UTC"
