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
from datetime import datetime


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

async def get_trades(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	symbol: str = None,
	status: str = None,
	date_from: datetime = None,
	date_to: datetime = None
):
	query = select(schemas.TradeORM).options(
		selectinload(schemas.TradeORM.signal),
		selectinload(schemas.TradeORM.user)
	)
	if symbol:
		query = query.filter(schemas.TradeORM.symbol == symbol)
	if status:
		query = query.filter(schemas.TradeORM.status == status)
	if date_from:
		query = query.filter(schemas.TradeORM.timestamp >= date_from)
	if date_to:
		query = query.filter(schemas.TradeORM.timestamp <= date_to)

	total_count = await db.scalar(
		select(func.count()).select_from(query.subquery())
	)

	result = await db.execute(query.offset(skip).limit(limit))
	trades = result.scalars().all()

	return {
		"items": trades,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}

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

async def patch_trade(db: AsyncSession, trade_id: int, updates: dict):
	"""Частичное обновление сделки (PATCH)."""
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
		if key in allowed_fields and value is not None:
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
		logger.error(f"Ошибка PATCH обновления сделки: {e}")
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


# ---------- Backtest Reports ----------
async def create_backtest_report(db: AsyncSession, report_data: dict) -> schemas.BacktestReport:
	"""Создать отчёт бэктеста и сохранить метрики."""
	try:
		report = schemas.BacktestReport(
			symbol=report_data["symbol"],
			strategy=report_data["strategy"],
			winrate=report_data["winrate"],
			avg_profit=report_data["avg_profit"],
			max_drawdown=report_data["max_drawdown"],
			sharpe=report_data["sharpe"],
			user_id=report_data.get("user_id", 1)
		)
		db.add(report)
		await db.commit()
		await db.refresh(report)
		return report
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания отчёта бэктеста: {e}")
		raise

async def get_backtest_reports(db: AsyncSession, symbol: str = None, strategy: str = None, user_id: int = None):
	query = select(schemas.BacktestReport)
	if symbol:
		query = query.filter(schemas.BacktestReport.symbol == symbol)
	if strategy:
		query = query.filter(schemas.BacktestReport.strategy == strategy)
	if user_id:
		query = query.filter(schemas.BacktestReport.user_id == user_id)
	result = await db.execute(query)
	return result.scalars().all()


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
			# 🔹 новые поля индикаторов
			obv=getattr(signal, "obv", None),
			stochastic=getattr(signal, "stochastic", None),
			vwap=getattr(signal, "vwap", None),
			ichimoku=getattr(signal, "ichimoku", None),
			volume=getattr(signal, "volume", None),
			bollinger=getattr(signal, "bollinger", None)
		)
		db.add(db_signal)
		await db.commit()
		await db.refresh(db_signal)
		return db_signal
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания сигнала: {e}")
		raise


async def get_signals(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	symbol: str = None,
	indicator: str = None,
	user_id: int = None,
	trade_id: int = None,
	date_from: datetime = None,
	date_to: datetime = None
):
	query = select(schemas.SignalORM).options(selectinload(schemas.SignalORM.user))
	if symbol:
		query = query.filter(schemas.SignalORM.symbol == symbol)
	if indicator:
		query = query.filter(schemas.SignalORM.indicator == indicator)
	if user_id:
		query = query.filter(schemas.SignalORM.user_id == user_id)
	if trade_id:
		query = query.filter(schemas.SignalORM.id == trade_id)
	if date_from:
		query = query.filter(schemas.SignalORM.timestamp >= date_from)
	if date_to:
		query = query.filter(schemas.SignalORM.timestamp <= date_to)

	total_count = await db.scalar(
		select(func.count()).select_from(query.subquery())
	)

	result = await db.execute(query.offset(skip).limit(limit))
	signals = result.scalars().all()

	return {
		"items": signals,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}

async def update_signal(db: AsyncSession, signal_id: int, updates: dict):
	result = await db.execute(select(schemas.SignalORM).filter(schemas.SignalORM.id == signal_id))
	db_signal = result.scalars().first()
	if not db_signal:
		return None

	allowed_fields = {
	"symbol", "indicator", "strength", "confidence",
	"source", "direction", "user_id",
	"obv", "stochastic", "vwap", "ichimoku", "volume", "bollinger"
}

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

async def patch_signal(db: AsyncSession, signal_id: int, updates: dict):
	"""Частичное обновление сигнала (PATCH)."""
	result = await db.execute(select(schemas.SignalORM).filter(schemas.SignalORM.id == signal_id))
	db_signal = result.scalars().first()
	if not db_signal:
		return None

	allowed_fields = {
	"symbol", "indicator", "strength", "confidence",
	"source", "direction", "user_id",
	"obv", "stochastic", "vwap", "ichimoku", "volume", "bollinger"
}

	for key, value in updates.items():
		if key in allowed_fields and value is not None:
			setattr(db_signal, key, value)

	try:
		await db.commit()
		await db.refresh(db_signal)
		return db_signal
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка PATCH обновления сигнала: {e}")
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

async def get_users(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	username: str = None,
	role: str = None
):
	query = select(schemas.UserORM)
	if username:
		query = query.filter(schemas.UserORM.username.ilike(f"%{username}%"))
	if role:
		query = query.filter(schemas.UserORM.role == role)

	# Подсчёт общего количества пользователей
	total_count = await db.scalar(
		select(func.count()).select_from(query.subquery())
	)

	result = await db.execute(query.offset(skip).limit(limit))
	users = result.scalars().all()

	return {
		"items": users,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}


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

async def get_indicator_by_id(db: AsyncSession, indicator_id: int) -> schemas.IndicatorORM | None:
	"""Получить индикатор по его ID."""
	result = await db.execute(select(schemas.IndicatorORM).filter(schemas.IndicatorORM.id == indicator_id))
	return result.scalars().first()

async def get_indicators(
	db: AsyncSession,
	pair: str = None,
	name: str = None,
	date_from: datetime = None,
	date_to: datetime = None,
	skip: int = 0,
	limit: int = 100
):
	"""Получить список индикаторов с фильтрацией и пагинацией."""
	query = select(schemas.IndicatorORM)
	if pair:
		query = query.filter(schemas.IndicatorORM.pair == pair)
	if name:
		query = query.filter(schemas.IndicatorORM.name == name)
	if date_from:
		query = query.filter(schemas.IndicatorORM.timestamp >= date_from)
	if date_to:
		query = query.filter(schemas.IndicatorORM.timestamp <= date_to)

	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	indicators = result.scalars().all()

	return {
		"items": indicators,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}

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

# ---------- Strategies ----------
async def get_strategies(db: AsyncSession, skip: int = 0, limit: int = 100):
	query = select(schemas.StrategyORM)
	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	strategies = result.scalars().all()
	return {
		"items": strategies,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}

async def get_strategy_by_symbol(db: AsyncSession, symbol: str):
	result = await db.execute(select(schemas.StrategyORM).filter(schemas.StrategyORM.symbol == symbol))
	return result.scalars().first()

async def update_strategy(db: AsyncSession, symbol: str, updates: dict):
	result = await db.execute(select(schemas.StrategyORM).filter(schemas.StrategyORM.symbol == symbol))
	strategy = result.scalars().first()
	if not strategy:
		return None
	for key, value in updates.items():
		if hasattr(strategy, key):
			setattr(strategy, key, value)
	try:
		await db.commit()
		await db.refresh(strategy)
		return strategy
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления стратегии: {e}")
		raise

async def delete_strategy(db: AsyncSession, symbol: str):
	result = await db.execute(select(schemas.StrategyORM).filter(schemas.StrategyORM.symbol == symbol))
	strategy = result.scalars().first()
	if not strategy:
		return None
	await db.delete(strategy)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления стратегии: {e}")
		raise


# ---------- Refresh Tokens ----------
async def create_refresh_token(db: AsyncSession, user_id: int, token: str, expires_at: datetime) -> schemas.RefreshTokenORM:
	"""Сохранить refresh токен в БД."""
	try:
		db_token = schemas.RefreshTokenORM(
			user_id=user_id,
			token=token,
			expires_at=expires_at
		)
		db.add(db_token)
		await db.commit()
		await db.refresh(db_token)
		return db_token
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка сохранения refresh токена: {e}")
		raise

async def get_refresh_token(db: AsyncSession, token: str) -> schemas.RefreshTokenORM | None:
	"""Получить refresh токен по строке токена."""
	result = await db.execute(select(schemas.RefreshTokenORM).filter(schemas.RefreshTokenORM.token == token))
	return result.scalars().first()

async def delete_refresh_token(db: AsyncSession, token: str) -> bool:
	"""Удалить refresh токен по строке токена."""
	result = await db.execute(select(schemas.RefreshTokenORM).filter(schemas.RefreshTokenORM.token == token))
	db_token = result.scalars().first()
	if not db_token:
		return False
	await db.delete(db_token)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления refresh токена: {e}")
		raise

async def delete_tokens_by_user(db: AsyncSession, user_id: int) -> bool:
	"""Удалить все refresh токены пользователя (например, при logout)."""
	result = await db.execute(select(schemas.RefreshTokenORM).filter(schemas.RefreshTokenORM.user_id == user_id))
	tokens = result.scalars().all()
	if not tokens:
		return False
	for t in tokens:
		await db.delete(t)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления refresh токенов пользователя: {e}")
		raise
