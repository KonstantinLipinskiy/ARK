import os
from dotenv import load_dotenv
from pydantic import BaseSettings

load_dotenv()

class Settings(BaseSettings):
	API_KEY: str = os.getenv("API_KEY")
	API_SECRET: str = os.getenv("API_SECRET")
	DATABASE_URL: str = os.getenv("DATABASE_URL")

	ENV: str = os.getenv("ENV", "dev")  # dev/testnet/mainnet
	SQL_ECHO: bool = os.getenv("SQL_ECHO", "False").lower() == "true"

	TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
	TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID")

	EXCHANGE_CONFIG = {
		"name": "bybit",
		"api_key": API_KEY,
		"api_secret": API_SECRET,
		"mode": os.getenv("EXCHANGE_MODE", "testnet")
	}

	RISK_CONFIG = {
		"max_risk_per_trade": 0.01,
		"max_open_trades": 5,
		"max_daily_loss": 0.05
	}

settings = Settings()


RABBITMQ_CONFIG = {
	"host": os.getenv("RABBITMQ_HOST", "amqp://guest:guest@localhost/"),
	"queue_signals": os.getenv("RABBITMQ_QUEUE_SIGNALS", "signals"),
	"queue_trades": os.getenv("RABBITMQ_QUEUE_TRADES", "trades"),
}

REDIS_CONFIG = {
	"host": os.getenv("REDIS_HOST", "localhost"),
	"port": int(os.getenv("REDIS_PORT", 6379)),
	"db": int(os.getenv("REDIS_DB", 0)),
}


# 🔹 Конфигурация стратегий для валютных пар
STRATEGY_CONFIG = {
	"BTC/USDT": {
		"enabled_indicators": ["EMA", "RSI", "ATR", "OBV"],
		"ema_short": 12,
		"ema_long": 26,
		"rsi_period": 14,
		"atr_period": 14,
		"stop_loss": 0.02,
		"take_profit_targets": [0.02, 0.04, 0.06],
		"trailing_stop": True,
		"trailing_mode": "step"
	},
	"ETH/USDT": {
		"enabled_indicators": ["MACD", "Stochastic", "Bollinger", "Volume"],
		"macd_fast": 12,
		"macd_slow": 26,
		"macd_signal": 9,
		"stochastic_period": 14,
		"bollinger_period": 20,
		"stop_loss": 0.025,
		"take_profit_targets": [0.025, 0.05, 0.075],
		"trailing_stop": True,
		"trailing_mode": "step"
	},
	"BNB/USDT": {
		"enabled_indicators": ["EMA", "MACD", "ATR", "OBV"],
		"ema_short": 10,
		"ema_long": 30,
		"macd_fast": 12,
		"macd_slow": 26,
		"macd_signal": 9,
		"atr_period": 14,
		"stop_loss": 0.03,
		"take_profit_targets": [0.03, 0.06, 0.09],
		"trailing_stop": True,
		"trailing_mode": "step"
	},
	"SOL/USDT": {
		"enabled_indicators": ["EMA", "RSI", "Bollinger", "Volume"],
		"ema_short": 20,
		"ema_long": 50,
		"rsi_period": 14,
		"bollinger_period": 20,
		"stop_loss": 0.035,
		"take_profit_targets": [0.035, 0.07, 0.105],
		"trailing_stop": True,
		"trailing_mode": "step"
	},
	"ADA/USDT": {
		"enabled_indicators": ["MACD", "Stochastic", "ATR", "OBV"],
		"macd_fast": 12,
		"macd_slow": 26,
		"macd_signal": 9,
		"stochastic_period": 14,
		"atr_period": 14,
		"stop_loss": 0.04,
		"take_profit_targets": [0.04, 0.08, 0.12],
		"trailing_stop": True,
		"trailing_mode": "step"
	}
}


