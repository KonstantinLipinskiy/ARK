import os
import logging
import logging.config

def setup_logger(config_path: str = "logging.ini"):
	"""
	Настройка логирования из файла logging.ini.
	Автоматически создаёт папку logs, если её нет.
	"""
	# Создаём папку logs, если она отсутствует
	os.makedirs("logs", exist_ok=True)

	# Загружаем конфиг
	logging.config.fileConfig(config_path, disable_existing_loggers=False)

	# Возвращаем основной логгер arkbot
	return logging.getLogger("arkbot")

# Инициализация логгера при импорте
logger = setup_logger()

# Тестовые записи (можно убрать в продакшене)
logger.info("ARK Bot API запущен")
logger.debug("Отладка стратегии ETH/USDT")
