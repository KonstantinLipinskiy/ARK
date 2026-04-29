# app/utils/logger.py
import os
import logging
import logging.config
from app.services.telegram import send_trade_notification

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
def log_critical_error(message: str, **kwargs):
	"""
	Логирование критической ошибки + уведомление в Telegram.
	"""
	logger.critical(message, extra=kwargs)
	try:
		send_trade_notification(f"❌ CRITICAL ERROR: {message}")
	except Exception as e:
		logger.error(f"Failed to send Telegram alert: {e}")
