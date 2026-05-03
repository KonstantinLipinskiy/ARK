# app/db/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.db import schemas
from app.models.trade import Trade
from app.models.signal import Signal
from app.models.user import User
from app.utils.logger import logger

# ---------- Trades ----------
async def create_trade(db: AsyncSession, trade: Trade) -> schemas.TradeORM:
	try:
		db_trade = schemas.TradeORM(
			symbol=trade.symbol,
			side=trade.side,
			amount=trade.amount,
			price=trade.price,
			status=trade.status,
			signal_id=trade.signal_id,
			user_id=trade.user_id
		)
		db.add(db_trade)
		await db.commit()
		await db.refresh(db_trade)
		return db_trade
	except IntegrityError as e:
		await db.rollback()
		logger.error(f"Ошибка уникальности при создании сделки: {e}")
		raise
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка БД при создании сделки: {e}")
		raise

async def get_trades(db: AsyncSession, skip: int = 0, limit: int = 100, symbol: str = None, status: str = None):
	query = select(schemas.TradeORM).options(selectinload(schemas.TradeORM.signal), selectinload(schemas.TradeORM.user))
	if symbol:
		query = query.filter(schemas.TradeORM.symbol == symbol)
	if status:
		query = query.filter(schemas.TradeORM.status == status)
	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

async def update_trade(db: AsyncSession, trade_id: int, updates: dict):
	result = await db.execute(select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id))
	db_trade = result.scalars().first()
	if not db_trade:
		return None
	for key, value in updates.items():
		setattr(db_trade, key, value)
	try:
		await db.commit()
		await db.refresh(db_trade)
		return db_trade
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления сделки: {e}")
		raise

async def delete_trade(db: AsyncSession, trade_id: int):
	result = await db.execute(select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id))
	db_trade = result.scalars().first()
	if not db_trade:
		return None
	await db.delete(db_trade)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления сделки: {e}")
		raise

# ---------- Signals ----------
async def create_signal(db: AsyncSession, signal: Signal) -> schemas.SignalORM:
	try:
		db_signal = schemas.SignalORM(
			symbol=signal.symbol,
			indicator=signal.indicator,
			strength=signal.strength,
			direction=signal.direction,
			user_id=signal.user_id
		)
		db.add(db_signal)
		await db.commit()
		await db.refresh(db_signal)
		return db_signal
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания сигнала: {e}")
		raise

async def get_signals(db: AsyncSession, skip: int = 0, limit: int = 100, symbol: str = None, indicator: str = None):
	query = select(schemas.SignalORM).options(selectinload(schemas.SignalORM.user))
	if symbol:
		query = query.filter(schemas.SignalORM.symbol == symbol)
	if indicator:
		query = query.filter(schemas.SignalORM.indicator == indicator)
	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

async def update_signal(db: AsyncSession, signal_id: int, updates: dict):
	result = await db.execute(select(schemas.SignalORM).filter(schemas.SignalORM.id == signal_id))
	db_signal = result.scalars().first()
	if not db_signal:
		return None
	for key, value in updates.items():
		setattr(db_signal, key, value)
	try:
		await db.commit()
		await db.refresh(db_signal)
		return db_signal
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления сигнала: {e}")
		raise

async def delete_signal(db: AsyncSession, signal_id: int):
	result = await db.execute(select(schemas.SignalORM).filter(schemas.SignalORM.id == signal_id))
	db_signal = result.scalars().first()
	if not db_signal:
		return None
	await db.delete(db_signal)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления сигнала: {e}")
		raise

# ---------- Users ----------
async def create_user(db: AsyncSession, user: User) -> schemas.UserORM:
	try:
		db_user = schemas.UserORM(
			username=user.username,
			email=user.email,
			role=user.role
		)
		db.add(db_user)
		await db.commit()
		await db.refresh(db_user)
		return db_user
	except IntegrityError as e:
		await db.rollback()
		logger.error(f"Ошибка уникальности при создании пользователя: {e}")
		raise
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания пользователя: {e}")
		raise

async def get_user_by_username(db: AsyncSession, username: str):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.username == username))
	return result.scalars().first()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100):
	result = await db.execute(select(schemas.UserORM).offset(skip).limit(limit))
	return result.scalars().all()

async def update_user(db: AsyncSession, user_id: int, updates: dict):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None
	for key, value in updates.items():
		setattr(db_user, key, value)
	try:
		await db.commit()
		await db.refresh(db_user)
		return db_user
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления пользователя: {e}")
		raise

async def delete_user(db: AsyncSession, user_id: int):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None
	await db.delete(db_user)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления пользователя: {e}")
		raise

# ---------- Аналитика ----------
async def get_trade_statistics(db: AsyncSession, user_id: int = None):
	query = select(schemas.TradeORM)
	if user_id:
		query = query.filter(schemas.TradeORM.user_id == user_id)
	result = await db.execute(query)
	trades = result.scalars().all()
	from app.utils.metrics import calculate_metrics
	return calculate_metrics(trades)
