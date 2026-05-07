import os
from dotenv import load_dotenv
from typing import ClassVar
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
	API_KEY: str = os.getenv("API_KEY")
	API_SECRET: str = os.getenv("API_SECRET")
	DATABASE_URL: str = os.getenv("DATABASE_URL")

	ENV: str = os.getenv("ENV", "dev")  # dev / mainnet / testnet
	SQL_ECHO: bool = os.getenv("SQL_ECHO", "False").lower() == "true"

	TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
	TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID")

	TRADING_MODE: str = os.getenv("TRADING_MODE", "spot")  # spot / futures
	USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"

	# 🔹 JWT настройки
	JWT_SECRET: str = os.getenv("JWT_SECRET", "default_secret")
	JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
	JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 60))

	# 🔹 Централизованная конфигурация биржи
	EXCHANGE_CONFIG: ClassVar[dict] = {
		"name": "bybit",
		"api_key": os.getenv("API_KEY"),
		"api_secret": os.getenv("API_SECRET"),
		"mode": "testnet" if os.getenv("USE_TESTNET", "false").lower() == "true" else "mainnet",
		"market_type": os.getenv("TRADING_MODE", "spot"),
	}

	ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")


settings = Settings()

DATABASE_URL = settings.DATABASE_URL


RABBITMQ_CONFIG = {
	"host": os.getenv("RABBITMQ_HOST", "amqp://guest:guest@localhost/"),
	"queue_signals": os.getenv("RABBITMQ_QUEUE_SIGNALS", "signals"),
	"queue_trades": os.getenv("RABBITMQ_QUEUE_TRADES", "trades"),
	"queue_indicators": os.getenv("RABBITMQ_QUEUE_INDICATORS", "indicators_queue"),
}


REDIS_CONFIG = {
	"host": os.getenv("REDIS_HOST", "localhost"),
	"port": int(os.getenv("REDIS_PORT", 6379)),
	"db": int(os.getenv("REDIS_DB", 0)),
}


# Это нужно будер реализлвать при деплоии

# 6.	Безопасность (усиление)
# o	Подключить AWS Secrets Manager или Docker secrets для хранения ключей.
# o	Добавить проверку, чтобы ключи не попадали в логи.
# o	При необходимости — шифровать .env.
