import os
import logging
from logging.handlers import TimedRotatingFileHandler
from app.services.telegram import telegram_service

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger():
    """
    Настройка логирования:
    - Ротация логов (ежедневно)
    - Разделение логов (общие, ошибки, сделки)
    - Расширенный формат (user_id, symbol, trade_id)
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

    logger = logging.getLogger("arkbot")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(general_handler)
    logger.addHandler(error_handler)
    logger.addHandler(trades_handler)

    return logger

# Инициализация логгера
logger = setup_logger()

async def log_critical_error(message: str, **kwargs):
    logger.critical(message, extra=kwargs)
    try:
        await telegram_service.send_message_by_id(
            telegram_id=os.getenv("ADMIN_TELEGRAM_ID", ""),
            text=f"❌ CRITICAL ERROR: {message}"
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
