from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, func
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
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	status = Column(Enum(TradeStatus), default=TradeStatus.open)

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
	role = Column(Enum(UserRole), default=UserRole.trader)
	status = Column(Enum(UserStatus), default=UserStatus.active, index=True)
	telegram_id = Column(String(50), unique=True, index=True)
	password_hash = Column(String(255), nullable=False)
	created_at = Column(DateTime, server_default=func.now())

	# связи
	trades = relationship("TradeORM", back_populates="user", cascade="all, delete-orphan")
	signals = relationship("SignalORM", back_populates="user", cascade="all, delete-orphan")
	backtest_reports = relationship("BacktestReport", back_populates="user", cascade="all, delete-orphan")

# --- Таблица логов риск-менеджмента ---
class RiskLog(Base):
	__tablename__ = "risk_logs"

	id = Column(Integer, primary_key=True, index=True)
	reason = Column(String(255), nullable=False)              # причина нарушения
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
