# app/utils/logger.py
import os
import logging
import logging.config
from app.services.telegram import telegram_service

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(config_path: str = "logging.ini"):
	"""
	Настройка логирования:
	- Подключение конфигурации из logging.ini
	- Возможность расширять кастомными хендлерами (например, Telegram)
	"""
	logging.config.fileConfig(config_path, disable_existing_loggers=False)
	logger = logging.getLogger("arkbot")
	return logger

# Инициализация логгера
logger = setup_logger()

# 🔹 Критические ошибки + уведомление в Telegram
async def log_critical_error(message: str, **kwargs):
	"""
	Логирование критической ошибки + уведомление в Telegram.
	"""
	logger.critical(message, extra=kwargs)
	try:
		# Отправляем уведомление администратору через Telegram
		await telegram_service.send_message_by_id(
			telegram_id=os.getenv("ADMIN_TELEGRAM_ID", ""),
			text=f"❌ CRITICAL ERROR: {message}"
		)
	except Exception as e:
		logger.error(f"Failed to send Telegram alert: {e}")

# 🔹 Универсальные методы для удобства
def log_info(message: str, **kwargs):
	"""
	Логирование информационного сообщения.
	"""
	logger.info(message, extra=kwargs)

def log_error(message: str, **kwargs):
	"""
	Логирование ошибки.
	"""
	logger.error(message, extra=kwargs)

def log_warning(message: str, **kwargs):
	"""
	Логирование предупреждения.
	"""
	logger.warning(message, extra=kwargs)
