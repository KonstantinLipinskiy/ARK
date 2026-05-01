from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.db.base import Base

# Enum для статуса сделки
class TradeStatus(enum.Enum):
	open = "open"
	closed = "closed"
	cancelled = "cancelled"

# Enum для направления сигнала
class SignalDirection(enum.Enum):
	buy = "buy"
	sell = "sell"

# Enum для роли пользователя
class UserRole(enum.Enum):
	admin = "admin"
	trader = "trader"

# Таблица сделок
class TradeORM(Base):
	__tablename__ = "trades"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	side = Column(String(10), nullable=False)   # buy/sell
	amount = Column(Float, nullable=False)
	price = Column(Float, nullable=False)
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	status = Column(Enum(TradeStatus), default=TradeStatus.open)

	# связь с пользователем
	user_id = Column(Integer, ForeignKey("users.id"))
	user = relationship("UserORM", back_populates="trades")

# Таблица сигналов
class SignalORM(Base):
	__tablename__ = "signals"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String(20), nullable=False, index=True)
	indicator = Column(String(50), nullable=False)
	strength = Column(Float, nullable=False)
	timestamp = Column(DateTime, server_default=func.now(), index=True)
	direction = Column(Enum(SignalDirection), nullable=False)

	# связь с пользователем (кто сгенерировал сигнал)
	user_id = Column(Integer, ForeignKey("users.id"))
	user = relationship("UserORM", back_populates="signals")

# Таблица пользователей
class UserORM(Base):
	__tablename__ = "users"

	id = Column(Integer, primary_key=True, index=True)
	username = Column(String(50), unique=True, nullable=False, index=True)
	email = Column(String(255), unique=True, nullable=False, index=True)
	role = Column(Enum(UserRole), default=UserRole.admin)
	created_at = Column(DateTime, server_default=func.now())

	# связи
	trades = relationship("TradeORM", back_populates="user")
	signals = relationship("SignalORM", back_populates="user")

# Таблица логов риск-менеджмента
class RiskLog(Base):
	__tablename__ = "risk_logs"

	id = Column(Integer, primary_key=True, index=True)
	reason = Column(String(255), nullable=False)              # причина нарушения
	timestamp = Column(DateTime, server_default=func.now())   # когда произошло