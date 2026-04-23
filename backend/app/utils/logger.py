import logging
import logging.config

def setup_logger(config_path: str = "logging.ini"):
	"""
	Настройка логирования из файла logging.ini
	"""
	logging.config.fileConfig(config_path, disable_existing_loggers=False)
	logger = logging.getLogger("arkbot")
	return logger

# Инициализация логгера при импорте
logger = setup_logger()

from app.utils.logger import logger

logger.info("ARK Bot API запущен")
logger.debug("Отладка стратегии ETH/USDT")
