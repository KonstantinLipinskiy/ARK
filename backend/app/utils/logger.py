# app/utils/logger.py
import os
import logging
import json
import asyncio
from logging.config import fileConfig
from app.services.telegram import telegram_service
from app.config import settings

# -------------------------------------------------------------------
# Кастомный TelegramHandler (обновлённый)
# -------------------------------------------------------------------
class TelegramHandler(logging.Handler):
	"""
	Кастомный хендлер для отправки CRITICAL ошибок в Telegram.
	Использует run_coroutine_threadsafe для неблокирующей отправки.
	"""
	def __init__(self, telegram_id: str = None, level=logging.CRITICAL):
		super().__init__(level)
		# Берём ID либо из аргумента, либо из settings
		self.telegram_id = telegram_id or settings.ADMIN_TELEGRAM_ID

	def emit(self, record):
		try:
			log_entry = self.format(record)
			if self.telegram_id:
				loop = asyncio.get_event_loop()
				coro = telegram_service.send_message_by_id(
					telegram_id=self.telegram_id,
					text=f"❌ CRITICAL ERROR: {log_entry}"
				)
				if loop.is_running():
					asyncio.run_coroutine_threadsafe(coro, loop)
				else:
					loop.run_until_complete(coro)
		except Exception as e:
			logging.error(f"Failed to send Telegram alert: {e}")

# -------------------------------------------------------------------
# JSON Formatter для Qdrant логов
# -------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
	def format(self, record):
		log_record = {
			"timestamp": self.formatTime(record, self.datefmt),
			"level": record.levelname,
			"logger": record.name,
			"message": record.getMessage(),
			"service": "Qdrant",
			"operation": getattr(record, "operation", None),
			"collection": getattr(record, "collection", None),
		}
		return json.dumps(log_record, ensure_ascii=False)

# -------------------------------------------------------------------
# JSON Formatter для метрик (Prometheus/Grafana)
# -------------------------------------------------------------------
class MetricsJSONFormatter(logging.Formatter):
	def format(self, record):
		log_record = {
			"timestamp": self.formatTime(record, self.datefmt),
			"level": record.levelname,
			"metric": getattr(record, "metric", None),
			"value": getattr(record, "value", None),
			"symbol": getattr(record, "symbol", None),
		}
		return json.dumps(log_record, ensure_ascii=False)

# -------------------------------------------------------------------
# Настройка логирования через logging.ini
# -------------------------------------------------------------------
def setup_logger():
	# Загружаем конфиг из logging.ini
	fileConfig("logging.ini", disable_existing_loggers=False)

	# Основной логгер
	logger = logging.getLogger("arkbot")

	# Логгер для метрик
	metrics_logger = logging.getLogger("metrics")
	metrics_handler = logging.FileHandler(settings.METRICS_LOG)
	metrics_handler.setFormatter(MetricsJSONFormatter())
	metrics_logger.addHandler(metrics_handler)
	metrics_logger.setLevel(logging.INFO)

	# Добавляем кастомный TelegramHandler (если не подключён через ini)
	if not any(isinstance(h, TelegramHandler) for h in logger.handlers):
		telegram_handler = TelegramHandler()
		telegram_handler.setLevel(logging.CRITICAL)
		logger.addHandler(telegram_handler)

	return logger, metrics_logger

# -------------------------------------------------------------------
# Инициализация логгеров
# -------------------------------------------------------------------
logger, metrics_logger = setup_logger()

# -------------------------------------------------------------------
# Асинхронная функция для CRITICAL ошибок
# -------------------------------------------------------------------
async def log_critical_error(message: str, **kwargs):
	"""
	Логирование критической ошибки + отправка уведомления в Telegram.
	"""
	logger.critical(message, extra=kwargs)
	try:
		await telegram_service.send_message_by_id(
			telegram_id=settings.ADMIN_TELEGRAM_ID,
			text=f"❌ CRITICAL ERROR: {message}"
		)
	except Exception as e:
		logger.error(f"Failed to send Telegram alert: {e}")

# -------------------------------------------------------------------
# Централизованное логирование событий
# -------------------------------------------------------------------
def log_order_error(context: str, error: Exception, **kwargs):
	logger.error(f"❌ {context} error: {error}", extra=kwargs)

def log_risk_violation(symbol: str, reason: str, **kwargs):
	logger.warning(f"⚠️ Risk violation: {reason} | symbol={symbol}", extra=kwargs)

def log_signal_rejected(symbol: str, confidence: float, **kwargs):
	logger.info(f"🚫 Signal rejected: {symbol} | confidence={confidence:.2f}", extra=kwargs)

# -------------------------------------------------------------------
# Логирование загрузки ML модели
# -------------------------------------------------------------------
def log_model_load(model_type: str, path: str, params: dict):
	"""
	Логирование информации о загруженной ML модели.
	"""
	logger.info(
		f"ML модель загружена: type={model_type}, path={path}, params={params}",
		extra={"operation": "load_model", "collection": "ml_models"}
	)
