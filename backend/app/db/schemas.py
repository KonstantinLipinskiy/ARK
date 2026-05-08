# app/db/schemas.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, func, Boolean, JSON
from sqlalchemy.orm import relationship
import enum
from app.db.base import Base

# --- Enum'ы ---
class TradeStatus(enum.Enum):
	open = "open"
	closed = "closed"
	cancelled = "cancelled"

class SignalDirection(enum.Enum):
	buy = "buy"
	sell = "sell"

class UserRole(enum.Enum):
	admin = "admin"
	trader = "trader"

class UserStatus(enum.Enum):
	active = "active"
	blocked = "blocked"

# --- Таблица сделок ---
class TradeORM(Base):
	__tablename__ = "trades"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	side = Column(String(10), nullable=False)   # buy/sell
	amount = Column(Float, nullable=False)
	price = Column(Float, nullable=False)
	entry_price = Column(Float)                 # цена входа
	exit_price = Column(Float)                  # цена выхода
	profit_loss = Column(Float)                 # PnL
	leverage = Column(Float, default=1.0)       # плечо
	stop_loss = Column(Float)                   # стоп-лосс %
	take_profit = Column(Float)                 # тейк-профит %
	confidence_score = Column(Float)            # доверие ML модели
	risk_reason = Column(String(255))           # причина отказа при валидации риска
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	status = Column(Enum(TradeStatus), default=TradeStatus.open)

	# 🔹 новое поле для синхронизации с биржей
	exchange_order_id = Column(String(50), unique=True, index=True)

	# связи
	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="trades")

	signal_id = Column(Integer, ForeignKey("signals.id", ondelete="SET NULL"), index=True)
	signal = relationship("SignalORM", back_populates="trades")


# --- Таблица сигналов ---
class SignalORM(Base):
	__tablename__ = "signals"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	indicator = Column(String(50), nullable=False)
	strength = Column(Float, nullable=False)
	confidence = Column(Float)                  # доверие к сигналу
	source = Column(String(50))                 # стратегия или внешний сервис
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	direction = Column(Enum(SignalDirection), nullable=False)

	# связи
	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="signals")

	trades = relationship("TradeORM", back_populates="signal", cascade="all, delete-orphan")


# --- Таблица пользователей ---
class UserORM(Base):
	__tablename__ = "users"

	id = Column(Integer, primary_key=True, index=True)
	username = Column(String(50), unique=True, nullable=False, index=True)
	email = Column(String(255), unique=True, nullable=False, index=True)
	role = Column(Enum(UserRole), default=UserRole.trader, nullable=False)
	status = Column(Enum(UserStatus), default=UserStatus.active, nullable=False, index=True)

	# 🔹 поля для аутентификации
	password_hash = Column(String(255), nullable=False)
	salt = Column(String(255), nullable=False)

	# 🔹 интеграция
	telegram_id = Column(String(50), unique=True, index=True)

	# 🔹 метаданные
	created_at = Column(DateTime, server_default=func.now())
	last_login = Column(DateTime, nullable=True)
	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

	# 🔹 настройки пользователя
	settings = Column(JSON, default={})

	# связи
	trades = relationship("TradeORM", back_populates="user", cascade="all, delete-orphan")
	signals = relationship("SignalORM", back_populates="user", cascade="all, delete-orphan")
	backtest_reports = relationship("BacktestReport", back_populates="user", cascade="all, delete-orphan")


# --- Таблица логов риск-менеджмента ---
class RiskLog(Base):
	__tablename__ = "risk_logs"

	id = Column(Integer, primary_key=True, index=True)
	reason = Column(String(255), nullable=False)              # причина нарушения
	symbol = Column(String(20), nullable=True)                # символ сделки
	position_size = Column(Float, nullable=True)              # размер позиции
	deposit = Column(Float, nullable=True)                    # депозит
	timestamp = Column(DateTime, server_default=func.now())   # когда произошло


# --- Таблица отчётов бэктеста ---
class BacktestReport(Base):
	__tablename__ = "backtest_reports"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)          # пара (BTC/USDT)
	strategy = Column(String(50), nullable=False, index=True)        # название стратегии (EMA+RSI)
	winrate = Column(Float, nullable=False)                          # винрейт %
	avg_profit = Column(Float, nullable=False)                       # средний профит
	max_drawdown = Column(Float, nullable=False)                     # максимальная просадка
	sharpe = Column(Float, nullable=False)                           # Sharpe ratio
	created_at = Column(DateTime, server_default=func.now())         # дата запуска бэктеста

	# связь с пользователем
	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="backtest_reports")


# --- Таблица стратегий ---
class StrategyORM(Base):
	__tablename__ = "strategies"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)              # BTC/USDT, ETH/USDT
	enabled_indicators = Column(JSON, nullable=False)    # ["EMA", "RSI", "ATR"]
	entry_conditions = Column(JSON, nullable=True)       # [["EMA", "RSI"], ["MACD"]]

	# параметры индикаторов
	ema_short = Column(Integer, nullable=True)
	ema_long = Column(Integer, nullable=True)
	rsi_period = Column(Integer, nullable=True)
	atr_period = Column(Integer, nullable=True)
	macd_fast = Column(Integer, nullable=True)
	macd_slow = Column(Integer, nullable=True)
	macd_signal = Column(Integer, nullable=True)
	stochastic_period = Column(Integer, nullable=True)
	bollinger_period = Column(Integer, nullable=True)

	# риск-менеджмент
	stop_loss = Column(Float, nullable=False)
	take_profit_targets = Column(JSON, nullable=False)   # [0.02, 0.04, 0.06]
	take_profit_distribution = Column(JSON, nullable=True)
	trailing_stop = Column(Boolean, default=False)
	trailing_mode = Column(String, default="step")

	# аллокация и плечо
	allocation_percent = Column(Float, nullable=False)
	leverage = Column(Integer, default=1)

	# 🔹 новый параметр влияния силы сигнала
	strength_multiplier = Column(Float, nullable=False, default=1.0)


# --- Таблица настроек риск-менеджмента ---
class RiskSettingsORM(Base):
	__tablename__ = "risk_settings"

	id = Column(Integer, primary_key=True, index=True)

	# 🔹 Основные лимиты
	max_risk_per_trade = Column(Float, nullable=False, default=0.01)
	max_open_trades = Column(Integer, nullable=False, default=5)
	max_daily_loss = Column(Float, nullable=False, default=0.05)
	max_leverage = Column(Integer, nullable=False, default=3)

	# 🔹 Дополнительные параметры
	cooldown_between_trades = Column(Integer, nullable=False, default=60)
	risk_reward_ratio = Column(Float, nullable=False, default=1.5)
	dynamic_allocation = Column(Boolean, nullable=False, default=False)

	# 🔹 Метаданные
	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# --- Таблица индикаторов ---
class IndicatorORM(Base):
	__tablename__ = "indicators"

	id = Column(Integer, primary_key=True, index=True)
	pair = Column(String(20), nullable=False, index=True)       # например BTC/USDT
	name = Column(String(50), nullable=False, index=True)       # EMA, RSI, MACD
	value = Column(String(255), nullable=False)                 # последнее рассчитанное значение
	timestamp = Column(DateTime, server_default=func.now(), index=True)

