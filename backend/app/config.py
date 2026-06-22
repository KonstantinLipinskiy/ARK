# app/config.py
import os
import json
from dotenv import load_dotenv
from typing import ClassVar
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    # --- API / DB ---
    API_KEY: str = os.getenv("API_KEY")
    API_SECRET: str = os.getenv("API_SECRET")
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    DATABASE_URL_TESTNET: str = os.getenv("DATABASE_URL_TESTNET", "")
    DATABASE_URL_MAINNET: str = os.getenv("DATABASE_URL_MAINNET", "")

    ENV: str = os.getenv("ENV", "dev")  # dev / mainnet / testnet
    SQL_ECHO: bool = os.getenv("SQL_ECHO", "False").lower() == "true"

    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID")
    ADMIN_TELEGRAM_ID: str = os.getenv("ADMIN_TELEGRAM_ID", "")

    TRADING_MODE: str = os.getenv("TRADING_MODE", "spot")
    USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"

    # --- JWT ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "default_secret")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 60))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

    # --- Exchange Config ---
    EXCHANGE_CONFIG: ClassVar[dict]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.EXCHANGE_CONFIG = {
            "name": os.getenv("EXCHANGE_NAME", "bybit"),
            "api_key": self.API_KEY,
            "api_secret": self.API_SECRET,
            "mode": "testnet" if self.USE_TESTNET else "mainnet",
            "market_type": self.TRADING_MODE,
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

    # --- ML Model Params ---
    MODEL_PARAMS: dict = json.loads(os.getenv("MODEL_PARAMS", '{"hidden_size": 128, "dropout": 0.4, "num_layers": 3}'))

    # --- Trading Defaults ---
    DEFAULT_DEPOSIT: float = float(os.getenv("DEFAULT_DEPOSIT", 1000))
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", 0.001))
    SLIPPAGE_TOLERANCE: float = float(os.getenv("SLIPPAGE_TOLERANCE", 0.0005))
    ATR_MULTIPLIER: float = float(os.getenv("ATR_MULTIPLIER", 2.0))
    SIGNAL_STRENGTH_MULTIPLIER: float = float(os.getenv("SIGNAL_STRENGTH_MULTIPLIER", 1.0))

    # --- Risk Management ---
    MAX_OPEN_TRADES: int = int(os.getenv("MAX_OPEN_TRADES", 5))
    COOLDOWN_BETWEEN_TRADES: int = int(os.getenv("COOLDOWN_BETWEEN_TRADES", 60))  # seconds
    RISK_REWARD_RATIO: float = float(os.getenv("RISK_REWARD_RATIO", 1.5))

    # --- Broker ---
    BROKER_RETRIES: int = int(os.getenv("BROKER_RETRIES", 2))
    BROKER_BASE_DELAY: float = float(os.getenv("BROKER_BASE_DELAY", 1.0))

    # --- Export ---
    DEBUG_EXPORT: bool = os.getenv("DEBUG_EXPORT", "False").lower() in ("true", "1", "yes")
    EXPORT_FILENAME: str = os.getenv("EXPORT_FILENAME", "backtest_summary.xlsx")
    EXPORT_TIMESTAMP: bool = os.getenv("EXPORT_TIMESTAMP", "True").lower() in ("true", "1", "yes")

    # --- LLM Config ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "google/flan-t5-large")
    LLM_MODEL_PATH: str = os.getenv("LLM_MODEL_PATH", "./models/llama-7b.ggmlv3.q4_0.bin")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", 0.0))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", 1.0))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", 512))

    # --- Business Rules ---
    MIN_SIGNAL_STRENGTH: float = float(os.getenv("MIN_SIGNAL_STRENGTH", 0.5))
    MAX_LOSS_PER_TRADE: float = float(os.getenv("MAX_LOSS_PER_TRADE", 100.0))
    MAX_TOTAL_LOSS: float = float(os.getenv("MAX_TOTAL_LOSS", 500.0))
    ALLOW_TEST_SIGNALS: bool = os.getenv("ALLOW_TEST_SIGNALS", "False").lower() in ("true", "1", "yes")

    # --- Logging Paths ---
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    ARKBOT_LOG: str = os.getenv("ARKBOT_LOG", os.path.join(LOG_DIR, "arkbot.log"))
    ERROR_LOG: str = os.getenv("ERROR_LOG", os.path.join(LOG_DIR, "errors.log"))
    TRADES_LOG: str = os.getenv("TRADES_LOG", os.path.join(LOG_DIR, "trades.log"))
    RISK_LOG: str = os.getenv("RISK_LOG", os.path.join(LOG_DIR, "risk.log"))
    BROKER_LOG: str = os.getenv("BROKER_LOG", os.path.join(LOG_DIR, "broker.log"))
    METRICS_LOG: str = os.getenv("METRICS_LOG", os.path.join(LOG_DIR, "metrics.log"))
    LOG_METRICS_LEVEL: str = os.getenv("LOG_METRICS_LEVEL", "INFO")

    # --- Protected Routes ---
    PROTECTED_PATHS: list[str] = os.getenv("PROTECTED_PATHS", "/signals,/trades,/users,/indicators").split(",")

    # --- Fetch Data Defaults ---
    DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "1h")
    DEFAULT_DAYS: int = int(os.getenv("DEFAULT_DAYS", 60))
    DATA_DIR: str = os.getenv("DATA_DIR", "data")

    # --- DB Pool Settings ---
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 10))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", 20))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", 30))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", 1800))


settings = Settings()

# --- RabbitMQ ---
RABBITMQ_CONFIG = {
    "host": os.getenv("RABBITMQ_HOST", "amqp://guest:guest@localhost/"),
    "queue_signals": os.getenv("RABBITMQ_QUEUE_SIGNALS", "signals"),
    "queue_trades": os.getenv("RABBITMQ_QUEUE_TRADES", "trades"),
    "queue_indicators": os.getenv("RABBITMQ_QUEUE_INDICATORS", "indicators_queue"),
    "queue_telegram": os.getenv("RABBITMQ_QUEUE_TELEGRAM", "telegram_notifications"),
    "queue_backtest": os.getenv("RABBITMQ_QUEUE_BACKTEST", "backtest_queue"),
    "queue_agents": os.getenv("RABBITMQ_QUEUE_AGENTS", "agents_queue"),
    "queue_reports": os.getenv("RABBITMQ_QUEUE_REPORTS", "reports_queue"),
    "queue_alerts": os.getenv("RABBITMQ_QUEUE_ALERTS", "alerts_queue"),
    "queue_logs": os.getenv("RABBITMQ_QUEUE_LOGS", "logs_queue"),
    "exchange_type": os.getenv("RABBITMQ_EXCHANGE_TYPE", "direct"),
}

# --- Redis ---
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DB", 0)),
}
