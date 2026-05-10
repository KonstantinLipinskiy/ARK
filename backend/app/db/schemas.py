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

	exchange_order_id = Column(String(50), unique=True, index=True)

	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="trades")

	signal_id = Column(Integer, ForeignKey("signals.id", ondelete="SET NULL"), index=True)
	signal = relationship("SignalORM", back_populates="trades")


# --- Таблица тестовых сделок (бэктесты) ---
class BacktestTradeORM(Base):
	__tablename__ = "backtest_trades"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	side = Column(String(10), nullable=False)   # buy/sell
	amount = Column(Float, nullable=False)
	entry_price = Column(Float, nullable=False)
	exit_price = Column(Float, nullable=True)
	profit_loss = Column(Float, nullable=True)
	leverage = Column(Float, default=1.0)
	stop_loss = Column(Float, nullable=True)
	take_profit = Column(Float, nullable=True)
	confidence_score = Column(Float, nullable=True)
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	status = Column(Enum(TradeStatus), default=TradeStatus.open)

	# связь с пользователем
	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="backtest_trades")

	# связь с сигналом
	signal_id = Column(Integer, ForeignKey("signals.id", ondelete="SET NULL"), index=True)
	signal = relationship("SignalORM")


# --- Таблица сигналов ---
class SignalORM(Base):
	__tablename__ = "signals"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	indicator = Column(String(50), nullable=False)
	strength = Column(Float, nullable=False)
	confidence = Column(Float)
	source = Column(String(50))
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	direction = Column(Enum(SignalDirection), nullable=False)

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

	password_hash = Column(String(255), nullable=False)
	salt = Column(String(255), nullable=False)

	telegram_id = Column(String(50), unique=True, index=True)
	is_admin = Column(Boolean, default=False, nullable=False)

	created_at = Column(DateTime, server_default=func.now())
	last_login = Column(DateTime, nullable=True)
	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

	settings = Column(JSON, default={})

	trades = relationship("TradeORM", back_populates="user", cascade="all, delete-orphan")
	signals = relationship("SignalORM", back_populates="user", cascade="all, delete-orphan")
	backtest_reports = relationship("BacktestReport", back_populates="user", cascade="all, delete-orphan")
	backtest_trades = relationship("BacktestTradeORM", back_populates="user", cascade="all, delete-orphan")


# --- Таблица логов риск-менеджмента ---
class RiskLog(Base):
	__tablename__ = "risk_logs"

	id = Column(Integer, primary_key=True, index=True)
	reason = Column(String(255), nullable=False)
	symbol = Column(String(20), nullable=True)
	position_size = Column(Float, nullable=True)
	deposit = Column(Float, nullable=True)
	timestamp = Column(DateTime, server_default=func.now())


# --- Таблица отчётов бэктеста ---
class BacktestReport(Base):
	__tablename__ = "backtest_reports"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	strategy = Column(String(50), nullable=False, index=True)
	winrate = Column(Float, nullable=False)
	avg_profit = Column(Float, nullable=False)
	max_drawdown = Column(Float, nullable=False)
	sharpe = Column(Float, nullable=False)
	created_at = Column(DateTime, server_default=func.now())

	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="backtest_reports")


# --- Таблица стратегий ---
class StrategyORM(Base):
	__tablename__ = "strategies"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)
	enabled_indicators = Column(JSON, nullable=False)
	entry_conditions = Column(JSON, nullable=True)

	ema_short = Column(Integer, nullable=True)
	ema_long = Column(Integer, nullable=True)
	rsi_period = Column(Integer, nullable=True)
	atr_period = Column(Integer, nullable=True)
	macd_fast = Column(Integer, nullable=True)
	macd_slow = Column(Integer, nullable=True)
	macd_signal = Column(Integer, nullable=True)
	stochastic_period = Column(Integer, nullable=True)
	bollinger_period = Column(Integer, nullable=True)

	stop_loss = Column(Float, nullable=False)
	take_profit_targets = Column(JSON, nullable=False)
	take_profit_distribution = Column(JSON, nullable=True)
	trailing_stop = Column(Boolean, default=False)
	trailing_mode = Column(String, default="step")

	allocation_percent = Column(Float, nullable=False)
	leverage = Column(Integer, default=1)

	strength_multiplier = Column(Float, nullable=False, default=1.0)


# --- Таблица настроек риск-менеджмента ---
class RiskSettingsORM(Base):
	__tablename__ = "risk_settings"

	id = Column(Integer, primary_key=True, index=True)
	max_risk_per_trade = Column(Float, nullable=False, default=0.01)
	max_open_trades = Column(Integer, nullable=False, default=5)
	max_daily_loss = Column(Float, nullable=False, default=0.05)
	max_leverage = Column(Integer, nullable=False, default=3)

	cooldown_between_trades = Column(Integer, nullable=False, default=60)
	risk_reward_ratio = Column(Float, nullable=False, default=1.5)
	dynamic_allocation = Column(Boolean, nullable=False, default=False)

	updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# --- Таблица индикаторов ---
class IndicatorORM(Base):
	__tablename__ = "indicators"

	id = Column(Integer, primary_key=True, index=True)
	pair = Column(String(20), nullable=False, index=True)
	name = Column(String(50), nullable=False, index=True)
	value = Column(String(255), nullable=False)
	timestamp = Column(DateTime, server_default=func.now(), index=True)
