from sqlalchemy.orm import Session
from app.db import schemas
from app.models.trade import Trade
from app.models.signal import Signal
from app.models.user import User

# ---------- Trades ----------
def create_trade(db: Session, trade: Trade) -> schemas.TradeORM:
	db_trade = schemas.TradeORM(
		symbol=trade.symbol,
		side=trade.side,
		amount=trade.amount,
		price=trade.price,
		status=trade.status
	)
	db.add(db_trade)
	db.commit()
	db.refresh(db_trade)
	return db_trade

def get_trades(db: Session, skip: int = 0, limit: int = 100):
	return db.query(schemas.TradeORM).offset(skip).limit(limit).all()

# ---------- Signals ----------
def create_signal(db: Session, signal: Signal) -> schemas.SignalORM:
	db_signal = schemas.SignalORM(
		symbol=signal.symbol,
		indicator=signal.indicator,
		strength=signal.strength,
		direction=signal.direction
	)
	db.add(db_signal)
	db.commit()
	db.refresh(db_signal)
	return db_signal

def get_signals(db: Session, skip: int = 0, limit: int = 100):
	return db.query(schemas.SignalORM).offset(skip).limit(limit).all()

# ---------- Users ----------
def create_user(db: Session, user: User) -> schemas.UserORM:
	db_user = schemas.UserORM(
		username=user.username,
		email=user.email,
		role=user.role
	)
	db.add(db_user)
	db.commit()
	db.refresh(db_user)
	return db_user

def get_user_by_username(db: Session, username: str):
	return db.query(schemas.UserORM).filter(schemas.UserORM.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
	return db.query(schemas.UserORM).offset(skip).limit(limit).all()
