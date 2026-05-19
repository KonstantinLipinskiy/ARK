from celery import Celery
from app.config import settings

celery_app = Celery(
	"ark_bot",
	broker=settings.CELERY_BROKER_URL,
	backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.beat_schedule = {
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
}
celery_app.conf.timezone = "UTC"
