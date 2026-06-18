# app/config.py
import os
from dotenv import load_dotenv
from typing import ClassVar
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
	# --- API / DB ---
	API_KEY: str = os.getenv("API_KEY")
	API_SECRET: str = os.getenv("API_SECRET")
	DATABASE_URL: str = os.getenv("DATABASE_URL")

	ENV: str = os.getenv("ENV", "dev")  # dev / mainnet / testnet
	SQL_ECHO: bool = os.getenv("SQL_ECHO", "False").lower() == "true"

	TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
	TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID")

	TRADING_MODE: str = os.getenv("TRADING_MODE", "spot")  # spot / futures
	USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"

	# --- JWT ---
	JWT_SECRET: str = os.getenv("JWT_SECRET", "default_secret")
	JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
	JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 60))
	REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

	# --- Exchange Config ---
	EXCHANGE_CONFIG: ClassVar[dict] = {
		"name": "bybit",
		"api_key": os.getenv("API_KEY"),
		"api_secret": os.getenv("API_SECRET"),
		"mode": "testnet" if os.getenv("USE_TESTNET", "false").lower() == "true" else "mainnet",
		"market_type": os.getenv("TRADING_MODE", "spot"),
	}

	ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")

	# --- Qdrant ---
	QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
	QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
	QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "arkbot_vectors")
	QDRANT_VECTOR_SIZE: int = int(os.getenv("QDRANT_VECTOR_SIZE", 768))
	QDRANT_DISTANCE: str = os.getenv("QDRANT_DISTANCE", "COSINE")

	# --- Celery ---
	CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
	CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

	# --- NewsData.io ---
	NEWSDATA_API_KEY: str = os.getenv("NEWSDATA_API_KEY", "")

	# --- ML Hyperparameters ---
	ML_EPOCHS: int = int(os.getenv("ML_EPOCHS", 100))
	ML_LEARNING_RATE: float = float(os.getenv("ML_LEARNING_RATE", 0.0007))
	ML_DROPOUT: float = float(os.getenv("ML_DROPOUT", 0.4))
	ML_HIDDEN_SIZE: int = int(os.getenv("ML_HIDDEN_SIZE", 128))
	ML_NUM_LAYERS: int = int(os.getenv("ML_NUM_LAYERS", 3))
	ML_USE_CV: bool = os.getenv("ML_USE_CV", "True").lower() in ("true", "1", "yes")
	ML_CV_SPLITS: int = int(os.getenv("ML_CV_SPLITS", 5))

	# --- ML Model Config ---
	MODEL_TYPE: str = os.getenv("MODEL_TYPE", "sklearn")
	MODEL_PATH: str = os.getenv("MODEL_PATH", "models/sklearn_model.pkl")
	CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", 0.2))
	SIGNAL_MULTIPLIER: float = float(os.getenv("SIGNAL_MULTIPLIER", 2.0))
	AMOUNT_FACTOR: float = float(os.getenv("AMOUNT_FACTOR", 0.5))

	# --- Trading Defaults ---
	DEFAULT_DEPOSIT: float = float(os.getenv("DEFAULT_DEPOSIT", 1000))
	COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", 0.001))
	SLIPPAGE_TOLERANCE: float = float(os.getenv("SLIPPAGE_TOLERANCE", 0.0005))
	ATR_MULTIPLIER: float = float(os.getenv("ATR_MULTIPLIER", 2.0))

	# --- Broker ---
	BROKER_RETRIES: int = int(os.getenv("BROKER_RETRIES", 2))
	BROKER_BASE_DELAY: float = float(os.getenv("BROKER_BASE_DELAY", 1.0))

	# --- Export ---
	DEBUG_EXPORT: bool = os.getenv("DEBUG_EXPORT", "False").lower() in ("true", "1", "yes")
	EXPORT_FILENAME: str = os.getenv("EXPORT_FILENAME", "backtest_summary.xlsx")

settings = Settings()

# --- RabbitMQ ---
RABBITMQ_CONFIG = {
	"host": os.getenv("RABBITMQ_HOST", "amqp://guest:guest@localhost/"),
	"queue_signals": os.getenv("RABBITMQ_QUEUE_SIGNALS", "signals"),
	"queue_trades": os.getenv("RABBITMQ_QUEUE_TRADES", "trades"),
	"queue_indicators": os.getenv("RABBITMQ_QUEUE_INDICATORS", "indicators_queue"),
}

# --- Redis ---
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
