from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base

# Таблица сделок
class TradeORM(Base):
	__tablename__ = "trades"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)
	side = Column(String, nullable=False)   # buy/sell
	amount = Column(Float, nullable=False)
	price = Column(Float, nullable=False)
	timestamp = Column(DateTime, default=datetime.utcnow)
	status = Column(String, default="open")

# Таблица сигналов
class SignalORM(Base):
	__tablename__ = "signals"

	id = Column(Integer, primary_key=True, index=True)
	symbol = Column(String, nullable=False)
	indicator = Column(String, nullable=False)
	strength = Column(Float, nullable=False)
	timestamp = Column(DateTime, default=datetime.utcnow)
	direction = Column(String, nullable=False)  # buy/sell

# Таблица пользователей
class UserORM(Base):
	__tablename__ = "users"

	id = Column(Integer, primary_key=True, index=True)
	username = Column(String, unique=True, nullable=False)
	email = Column(String, unique=True, nullable=False)
	role = Column(String, default="admin")  # admin/trader
	created_at = Column(DateTime, default=datetime.utcnow)
