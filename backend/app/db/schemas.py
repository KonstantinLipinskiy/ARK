from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, func, Boolean, BigInteger, JSON
from sqlalchemy.orm import relationship
import enum
from app.db.base import Base


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

class TradeORM(Base):
	__tablename__ = "trades"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	side = Column(String(10), nullable=False)   # buy/sell
	amount = Column(Float, nullable=False)
	price = Column(Float, nullable=False)
	entry_price = Column(Float)
	exit_price = Column(Float)
	profit_loss = Column(Float)
	leverage = Column(Float, default=1.0)
	stop_loss = Column(Float)
	take_profit = Column(Float)
	confidence_score = Column(Float)
	risk_reason = Column(String(255))
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	status = Column(Enum(TradeStatus), default=TradeStatus.open)
	exchange_order_id = Column(String(50), unique=True, index=True)
	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="trades")
	signal_id = Column(Integer, ForeignKey("signals.id", ondelete="SET NULL"), index=True)
	signal = relationship("SignalORM", back_populates="trades")

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

	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="backtest_trades")

	signal_id = Column(Integer, ForeignKey("signals.id", ondelete="SET NULL"), index=True)
	signal = relationship("SignalORM", back_populates="backtest_trades")

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

	obv = Column(Float, nullable=True)
	stochastic = Column(Float, nullable=True)
	vwap = Column(Float, nullable=True)
	ichimoku = Column(Float, nullable=True)
	volume = Column(Float, nullable=True)
	bollinger = Column(Float, nullable=True)

	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="signals")

	trades = relationship("TradeORM", back_populates="signal", cascade="all, delete-orphan")

	backtest_trades = relationship("BacktestTradeORM", back_populates="signal", cascade="all, delete-orphan")

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

	refresh_tokens = relationship("RefreshTokenORM", back_populates="user", cascade="all, delete-orphan")

class RiskLog(Base):
	__tablename__ = "risk_logs"

	id = Column(Integer, primary_key=True, index=True)
	reason = Column(String(255), nullable=False)
	symbol = Column(String(20), nullable=True)
	position_size = Column(Float, nullable=True)
	deposit = Column(Float, nullable=True)
	timestamp = Column(DateTime, server_default=func.now())

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

class StrategyORM(Base):
	__tablename__ = "strategies"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)

	# --- Индикаторы и условия ---
	enabled_indicators = Column(JSON, nullable=False)   # список включённых индикаторов
	entry_conditions = Column(JSON, nullable=True)      # условия входа (комбинации индикаторов)

	# --- EMA / RSI / ATR ---
	ema_short = Column(Integer, nullable=True)
	ema_long = Column(Integer, nullable=True)
	rsi_period = Column(Integer, nullable=True)
	atr_period = Column(Integer, nullable=True)

	# --- MACD ---
	macd_fast = Column(Integer, nullable=True)
	macd_slow = Column(Integer, nullable=True)
	macd_signal = Column(Integer, nullable=True)

	# --- Stochastic ---
	stochastic_period = Column(Integer, nullable=True)

	# --- Bollinger Bands ---
	bollinger_period = Column(Integer, nullable=True)

	# --- OBV ---
	obv_enabled = Column(Boolean, default=False)

	# --- Volume SMA ---
	volume_period = Column(Integer, nullable=True)

	# --- VWAP ---
	vwap_enabled = Column(Boolean, default=False)

	# --- Ichimoku Cloud ---
	ichimoku_tenkan = Column(Integer, nullable=True, default=9)
	ichimoku_kijun = Column(Integer, nullable=True, default=26)
	ichimoku_senkou = Column(Integer, nullable=True, default=52)

	# --- Риск-менеджмент ---
	stop_loss = Column(Float, nullable=False)
	take_profit_targets = Column(JSON, nullable=False)
	take_profit_distribution = Column(JSON, nullable=True)

	trailing_stop = Column(Boolean, default=False)
	trailing_mode = Column(String, default="step")

	# --- Управление капиталом ---
	allocation_percent = Column(Float, nullable=False)
	leverage = Column(Integer, default=1)

	# --- Дополнительно ---
	strength_multiplier = Column(Float, nullable=False, default=1.0)
	enabled = Column(Boolean, default=True)  # 🔹 добавлено для симметрии

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

class IndicatorORM(Base):
	__tablename__ = "indicators"

	id = Column(Integer, primary_key=True, index=True)
	pair = Column(String(20), nullable=False, index=True)
	name = Column(String(50), nullable=False, index=True)
	value = Column(String(255), nullable=False)
	timestamp = Column(DateTime, server_default=func.now(), index=True)

class RefreshTokenORM(Base):
	__tablename__ = "refresh_tokens"

	id = Column(Integer, primary_key=True, index=True)
	token = Column(String(512), unique=True, nullable=False, index=True)
	created_at = Column(DateTime, server_default=func.now())
	expires_at = Column(DateTime, nullable=False)

	user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	user = relationship("UserORM", back_populates="refresh_tokens")

class OHLCVHourly(Base):
	__tablename__ = "ohlcv_hourly"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)          # валютная пара (BTC/USDT, ETH/USDT и т.д.)
	timestamp = Column(BigInteger, nullable=False)   # время свечи (Unix ms)
	open = Column(Float, nullable=False)
	high = Column(Float, nullable=False)
	low = Column(Float, nullable=False)
	close = Column(Float, nullable=False)
	volume = Column(Float, nullable=False)
