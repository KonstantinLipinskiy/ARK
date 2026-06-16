import os
import logging
import json
from logging.handlers import TimedRotatingFileHandler
from app.services.telegram import telegram_service

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Кастомный TelegramHandler
# -------------------------------------------------------------------
class TelegramHandler(logging.Handler):
	"""
	Кастомный хендлер для отправки CRITICAL ошибок в Telegram.
	"""
	def __init__(self, level=logging.CRITICAL):
		super().__init__(level)

	def emit(self, record):
		try:
			log_entry = self.format(record)
			telegram_id = os.getenv("ADMIN_TELEGRAM_ID", "")
			if telegram_id:
				import asyncio
				loop = asyncio.get_event_loop()
				if loop.is_running():
					asyncio.create_task(
						telegram_service.send_message_by_id(
							telegram_id=telegram_id,
							text=f"❌ CRITICAL ERROR: {log_entry}"
						)
					)
				else:
					loop.run_until_complete(
						telegram_service.send_message_by_id(
							telegram_id=telegram_id,
							text=f"❌ CRITICAL ERROR: {log_entry}"
						)
					)
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
# Настройка логирования
# -------------------------------------------------------------------
def setup_logger():
	"""
	Настройка логирования:
	- Ротация логов (ежедневно)
	- Разделение логов (общие, ошибки, сделки, Qdrant, ML)
	- Расширенный формат (user_id, symbol, trade_id)
	- Отправка CRITICAL ошибок в Telegram
	"""
	formatter = logging.Formatter(
		"%(asctime)s | %(levelname)s | %(name)s | "
		"user_id=%(user_id)s | symbol=%(symbol)s | trade_id=%(trade_id)s | %(message)s"
	)

	# Общий лог
	general_handler = TimedRotatingFileHandler(
		os.path.join(LOG_DIR, "arkbot.log"), when="midnight", backupCount=7, encoding="utf-8"
	)
	general_handler.setFormatter(formatter)
	general_handler.setLevel(logging.INFO)

	# Лог ошибок
	error_handler = TimedRotatingFileHandler(
		os.path.join(LOG_DIR, "errors.log"), when="midnight", backupCount=7, encoding="utf-8"
	)
	error_handler.setFormatter(formatter)
	error_handler.setLevel(logging.ERROR)

	# Лог сделок
	trades_handler = TimedRotatingFileHandler(
		os.path.join(LOG_DIR, "trades.log"), when="midnight", backupCount=7, encoding="utf-8"
	)
	trades_handler.setFormatter(formatter)
	trades_handler.setLevel(logging.INFO)

	# Лог ошибок Qdrant (JSON формат)
	qdrant_handler = TimedRotatingFileHandler(
		os.path.join(LOG_DIR, "qdrant.log"), when="midnight", backupCount=7, encoding="utf-8"
	)
	qdrant_handler.setFormatter(JSONFormatter())
	qdrant_handler.setLevel(logging.ERROR)

	# Лог ML моделей
	ml_handler = TimedRotatingFileHandler(
		os.path.join(LOG_DIR, "ml.log"), when="midnight", backupCount=7, encoding="utf-8"
	)
	ml_handler.setFormatter(formatter)
	ml_handler.setLevel(logging.INFO)

	# Telegram handler для CRITICAL ошибок
	telegram_handler = TelegramHandler()
	telegram_handler.setFormatter(formatter)
	telegram_handler.setLevel(logging.CRITICAL)

	logger = logging.getLogger("arkbot")
	logger.setLevel(logging.DEBUG)
	logger.addHandler(general_handler)
	logger.addHandler(error_handler)
	logger.addHandler(trades_handler)
	logger.addHandler(qdrant_handler)
	logger.addHandler(ml_handler)
	logger.addHandler(telegram_handler)

	return logger

# -------------------------------------------------------------------
# Инициализация логгера
# -------------------------------------------------------------------
logger = setup_logger()

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
			telegram_id=os.getenv("ADMIN_TELEGRAM_ID", ""),
			text=f"❌ CRITICAL ERROR: {message}"
		)
	except Exception as e:
		logger.error(f"Failed to send Telegram alert: {e}")

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
