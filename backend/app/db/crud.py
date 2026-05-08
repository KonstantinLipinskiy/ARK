# app/db/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import func
from app.db import schemas
from app.models.trade import Trade
from app.models.signal import Signal
from app.models.user import User, UserCreate
from app.utils.logger import logger
from app.config import settings
from app.utils.security import hash_password

# ---------- Trades ----------
async def create_trade(db: AsyncSession, trade: Trade) -> schemas.TradeORM:
	try:
		leverage = trade.leverage if trade.leverage else 1.0
		if settings.TRADING_MODE == "spot":
			leverage = 1.0

		db_trade = schemas.TradeORM(
			symbol=trade.symbol,
			side=trade.side,
			amount=trade.amount,
			price=trade.price,
			status=trade.status,
			signal_id=trade.signal_id,
			user_id=trade.user_id,
			entry_price=trade.entry_price,
			exit_price=trade.exit_price,
			profit_loss=trade.profit_loss,
			leverage=leverage,
			stop_loss=getattr(trade, "stop_loss", None),
			take_profit=getattr(trade, "take_profit", None),
			confidence_score=getattr(trade, "confidence_score", None),
			risk_reason=getattr(trade, "risk_reason", None),
			exchange_order_id=getattr(trade, "exchange_order_id", None)
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
	query = select(schemas.TradeORM).options(
		selectinload(schemas.TradeORM.signal),
		selectinload(schemas.TradeORM.user)
	)
	if symbol:
		query = query.filter(schemas.TradeORM.symbol == symbol)
	if status:
		query = query.filter(schemas.TradeORM.status == status)
	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

async def get_trades_by_user(db: AsyncSession, user_id: int):
	result = await db.execute(
		select(schemas.TradeORM).filter(schemas.TradeORM.user_id == user_id)
	)
	return result.scalars().all()

async def get_trades_by_signal(db: AsyncSession, signal_id: int):
	result = await db.execute(
		select(schemas.TradeORM).filter(schemas.TradeORM.signal_id == signal_id)
	)
	return result.scalars().all()

async def update_trade(db: AsyncSession, trade_id: int, updates: dict):
	result = await db.execute(select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id))
	db_trade = result.scalars().first()
	if not db_trade:
		return None

	allowed_fields = {
		"symbol", "side", "amount", "price", "status",
		"entry_price", "exit_price", "profit_loss", "leverage",
		"signal_id", "user_id", "exchange_order_id",
		"stop_loss", "take_profit", "confidence_score", "risk_reason"
	}
	for key, value in updates.items():
		if key in allowed_fields:
			setattr(db_trade, key, value)

	if "status" in updates and updates["status"] == "closed":
		if db_trade.entry_price and db_trade.exit_price:
			db_trade.profit_loss = (db_trade.exit_price - db_trade.entry_price) * db_trade.amount * db_trade.leverage

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

async def close_trade(db: AsyncSession, trade_id: int, exit_price: float):
	"""Закрыть сделку и рассчитать PnL."""
	result = await db.execute(select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id))
	db_trade = result.scalars().first()
	if not db_trade:
		return None
	db_trade.exit_price = exit_price
	db_trade.status = schemas.TradeStatus.closed
	if db_trade.entry_price and db_trade.exit_price:
		db_trade.profit_loss = (db_trade.exit_price - db_trade.entry_price) * db_trade.amount * db_trade.leverage
	try:
		await db.commit()
		await db.refresh(db_trade)
		return db_trade
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка закрытия сделки: {e}")
		raise

async def cancel_trade(db: AsyncSession, trade_id: int, reason: str = "Cancelled manually"):
	"""Отменить сделку с указанием причины."""
	result = await db.execute(select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id))
	db_trade = result.scalars().first()
	if not db_trade:
		return None
	db_trade.status = schemas.TradeStatus.cancelled
	db_trade.risk_reason = reason
	try:
		await db.commit()
		await db.refresh(db_trade)
		return db_trade
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка отмены сделки: {e}")
		raise

# ---------- Signals ----------
async def create_signal(db: AsyncSession, signal: Signal) -> schemas.SignalORM:
	try:
		db_signal = schemas.SignalORM(
			symbol=signal.symbol,
			indicator=signal.indicator,
			strength=signal.strength,
			direction=signal.direction,
			user_id=signal.user_id,
			confidence=signal.confidence,
			source=signal.source,
			probability=getattr(signal, "probability", None)
		)
		db.add(db_signal)
		await db.commit()
		await db.refresh(db_signal)
		return db_signal
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания сигнала: {e}")
		raise

async def get_signals(db: AsyncSession, skip: int = 0, limit: int = 100,
							symbol: str = None, indicator: str = None,
							user_id: int = None, trade_id: int = None):
	query = select(schemas.SignalORM).options(selectinload(schemas.SignalORM.user))
	if symbol:
		query = query.filter(schemas.SignalORM.symbol == symbol)
	if indicator:
		query = query.filter(schemas.SignalORM.indicator == indicator)
	if user_id:
		query = query.filter(schemas.SignalORM.user_id == user_id)
	if trade_id:
		query = query.filter(schemas.SignalORM.id == trade_id)
	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

async def update_signal(db: AsyncSession, signal_id: int, updates: dict):
	result = await db.execute(select(schemas.SignalORM).filter(schemas.SignalORM.id == signal_id))
	db_signal = result.scalars().first()
	if not db_signal:
		return None

	allowed_fields = {"symbol", "indicator", "strength", "confidence",
							"source", "direction", "user_id", "probability"}
	for key, value in updates.items():
		if key in allowed_fields:
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
async def create_user(db: AsyncSession, user: UserCreate) -> schemas.UserORM:
	try:
		salt, password_hash = hash_password(user.password)
		db_user = schemas.UserORM(
			username=user.username,
			email=user.email,
			role=user.role,
			status="active",
			password_hash=password_hash,
			salt=salt,
			telegram_id=user.telegram_id,
			settings=user.settings
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

async def get_user_by_email(db: AsyncSession, email: str):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.email == email))
	return result.scalars().first()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100):
	result = await db.execute(select(schemas.UserORM).offset(skip).limit(limit))
	return result.scalars().all()

async def update_user_status(db: AsyncSession, user_id: int, status: str):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None
	db_user.status = status
	try:
		await db.commit()
		await db.refresh(db_user)
		return db_user
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления статуса пользователя: {e}")
		raise

async def update_user(db: AsyncSession, user_id: int, updates: dict):
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None

	allowed_fields = {
		"username", "email", "role", "status",
		"telegram_id", "password_hash", "salt",
		"last_login", "updated_at", "settings"
	}
	for key, value in updates.items():
		if key in allowed_fields:
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

# ---------- Indicators ----------
async def save_indicator(db: AsyncSession, pair: str, name: str, value: str) -> schemas.IndicatorORM:
	"""Сохраняет рассчитанный индикатор в таблицу indicators."""
	try:
		indicator = schemas.IndicatorORM(pair=pair, name=name, value=value)
		db.add(indicator)
		await db.commit()
		await db.refresh(indicator)
		return indicator
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка сохранения индикатора: {e}")
		raise

async def get_indicators(db: AsyncSession, pair: str = None, name: str = None, skip: int = 0, limit: int = 100):
	query = select(schemas.IndicatorORM)
	if pair:
		query = query.filter(schemas.IndicatorORM.pair == pair)
	if name:
		query = query.filter(schemas.IndicatorORM.name == name)
	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

async def delete_indicator(db: AsyncSession, indicator_id: int):
	result = await db.execute(select(schemas.IndicatorORM).filter(schemas.IndicatorORM.id == indicator_id))
	db_indicator = result.scalars().first()
	if not db_indicator:
		return None
	await db.delete(db_indicator)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления индикатора: {e}")
		raise

# ---------- Analytics ----------
async def get_user_winrate(db: AsyncSession, user_id: int) -> float:
	"""Подсчёт винрейта пользователя (закрытые сделки с профитом / все закрытые сделки)."""
	result = await db.execute(
		select(schemas.TradeORM).filter(
			schemas.TradeORM.user_id == user_id,
			schemas.TradeORM.status == schemas.TradeStatus.closed
		)
	)
	trades = result.scalars().all()
	if not trades:
		return 0.0
	wins = sum(1 for t in trades if t.profit_loss and t.profit_loss > 0)
	return wins / len(trades)

async def get_average_profit(db: AsyncSession, user_id: int) -> float:
	"""Средний профит пользователя по закрытым сделкам."""
	result = await db.execute(
		select(schemas.TradeORM.profit_loss).filter(
			schemas.TradeORM.user_id == user_id,
			schemas.TradeORM.status == schemas.TradeStatus.closed
		)
	)
	profits = [p for p in result.scalars().all() if p is not None]
	if not profits:
		return 0.0
	return sum(profits) / len(profits)

async def count_signals_by_indicator(db: AsyncSession, indicator: str) -> int:
	"""Количество сигналов по конкретному индикатору."""
	result = await db.execute(
		select(func.count()).select_from(schemas.SignalORM).filter(
			schemas.SignalORM.indicator == indicator
		)
	)
	return result.scalar() or 0
