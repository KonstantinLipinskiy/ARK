#app/db/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import func
from app.db import schemas
from app.models.trade import Trade
from app.models.signal import Signal
from app.models.user import User, UserCreate, UserUpdate
from app.utils.logger import logger
from app.config import settings
from app.utils.security import hash_password
from datetime import datetime, timedelta, timezone


# ---------- Trades ----------
async def create_trade(db: AsyncSession, trade: Trade) -> schemas.TradeORM:
	try:
		# ⚙️ Корректируем плечо в зависимости от режима торговли
		leverage = trade.leverage if trade.leverage else 1.0
		if settings.TRADING_MODE == "spot":
			leverage = 1.0

		# ⚙️ Приведение статуса к Enum TradeStatus
		status = (
			schemas.TradeStatus(trade.status)
			if isinstance(trade.status, str)
			else trade.status
		)

		# ⚙️ Создание ORM объекта
		db_trade = schemas.TradeORM(
			symbol=trade.symbol,
			side=trade.side,
			amount=trade.amount,
			price=trade.price,
			status=status,
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
			exchange_order_id=getattr(trade, "exchange_order_id", None),
			news_sentiment=getattr(trade, "news_sentiment", None),
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
	user_id: int = None,
	signal_id: int = None,
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
		query = query.filter(schemas.TradeORM.status == schemas.TradeStatus(status) if isinstance(status, str) else status)
	if user_id:
		query = query.filter(schemas.TradeORM.user_id == user_id)
	if signal_id:
		query = query.filter(schemas.TradeORM.signal_id == signal_id)
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


async def get_trade_by_id(db: AsyncSession, trade_id: int) -> schemas.TradeORM | None:
	"""Получить сделку по её ID."""
	result = await db.execute(
		select(schemas.TradeORM).filter(schemas.TradeORM.id == trade_id)
	)
	return result.scalars().first()


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
		"stop_loss", "take_profit", "confidence_score", "risk_reason", "news_sentiment"
	}
	for key, value in updates.items():
		if key in allowed_fields:
			setattr(db_trade, key, value)

	if "status" in updates:
		new_status = updates["status"]
		if isinstance(new_status, str):
			new_status = schemas.TradeStatus(new_status)   # ✅ перевод строки в Enum
		db_trade.status = new_status
		if new_status == schemas.TradeStatus.closed:
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
		"stop_loss", "take_profit", "confidence_score", "risk_reason", "news_sentiment"
	}
	for key, value in updates.items():
		if key in allowed_fields and value is not None:
			setattr(db_trade, key, value)

	if "status" in updates:
		new_status = updates["status"]
		if isinstance(new_status, str):
			new_status = schemas.TradeStatus(new_status)   # ✅ перевод строки в Enum
		db_trade.status = new_status
		if new_status == schemas.TradeStatus.closed:
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
			avg_sentiment_win=report_data.get("avg_sentiment_win"),
			avg_sentiment_loss=report_data.get("avg_sentiment_loss"),
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
			obv=getattr(signal, "obv", None),
			stochastic=getattr(signal, "stochastic", None),
			vwap=getattr(signal, "vwap", None),
			ichimoku=getattr(signal, "ichimoku", None),
			volume=getattr(signal, "volume", None),
			bollinger=getattr(signal, "bollinger", None),
			news_sentiment=getattr(signal, "news_sentiment", None),  # ✅ добавлено
			status=getattr(signal, "status", schemas.SignalStatus.active)  # ✅ добавлено
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
	date_to: datetime = None,
	status: str = None   # ✅ добавлено
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
	if status:
		query = query.filter(
			schemas.SignalORM.status == schemas.SignalStatus(status) if isinstance(status, str) else status
		)

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
		"obv", "stochastic", "vwap", "ichimoku", "volume", "bollinger",
		"news_sentiment",  # ✅ добавлено
		"status"           # ✅ добавлено
	}

	for key, value in updates.items():
		if key in allowed_fields:
			if key == "status" and isinstance(value, str):
				value = schemas.SignalStatus(value)  # ✅ перевод строки в Enum
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
		"obv", "stochastic", "vwap", "ichimoku", "volume", "bollinger",
		"news_sentiment",  # ✅ добавлено
		"status"           # ✅ добавлено
	}

	for key, value in updates.items():
		if key in allowed_fields and value is not None:
			if key == "status" and isinstance(value, str):
				value = schemas.SignalStatus(value)  # ✅ перевод строки в Enum
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
	"""Создать нового пользователя."""
	try:
		salt, password_hash = hash_password(user.password)
		settings = user.settings or {}
		if "notifications_enabled" not in settings:
			settings["notifications_enabled"] = True

		role = schemas.UserRole(user.role) if isinstance(user.role, str) else user.role

		db_user = schemas.UserORM(
			username=user.username,
			email=user.email,
			role=role,
			status=schemas.UserStatus.active,
			password_hash=password_hash,
			salt=salt,
			telegram_id=user.telegram_id,
			is_admin=user.is_admin,   # ✅ добавлено
			settings=settings
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

async def get_user_by_id(db: AsyncSession, user_id: int) -> schemas.UserORM | None:
	"""Получить пользователя по ID."""
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	return result.scalars().first()


async def get_user_by_username(db: AsyncSession, username: str) -> schemas.UserORM | None:
	"""Получить пользователя по username."""
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.username == username))
	return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> schemas.UserORM | None:
	"""Получить пользователя по email."""
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.email == email))
	return result.scalars().first()


async def get_users(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	username: str = None,
	role: str = None
):
	"""Получить список пользователей с фильтрацией и пагинацией."""
	query = select(schemas.UserORM)
	if username:
		query = query.filter(schemas.UserORM.username.ilike(f"%{username}%"))
	if role:
		query = query.filter(schemas.UserORM.role == role)

	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	users = result.scalars().all()

	return {
		"items": users,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}


async def update_user_status(db: AsyncSession, user_id: int, status: str) -> schemas.UserORM | None:
	"""Обновить статус пользователя."""
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None
	db_user.status = schemas.UserStatus(status) if isinstance(status, str) else status  # ✅ Приведение к Enum
	try:
		await db.commit()
		await db.refresh(db_user)
		return db_user
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления статуса пользователя: {e}")
		raise


async def update_user(db: AsyncSession, user_id: int, updates: UserUpdate) -> schemas.UserORM | None:
	"""Обновить данные пользователя через UserUpdate."""
	result = await db.execute(select(schemas.UserORM).filter(schemas.UserORM.id == user_id))
	db_user = result.scalars().first()
	if not db_user:
		return None

	allowed_fields = {
		"username", "email", "role", "status",
		"telegram_id", "last_login", "updated_at",
		"is_admin", "settings"   # ✅ оставлены только безопасные поля
	}

	update_data = updates.dict(exclude_unset=True)

	for key, value in update_data.items():
		if key in allowed_fields:
			if key == "settings" and value:
				# обновляем словарь настроек вместо перезаписи
				db_user.settings.update(value)
			else:
				setattr(db_user, key, value)

	try:
		await db.commit()
		await db.refresh(db_user)
		return db_user
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления пользователя: {e}")
		raise


async def delete_user(db: AsyncSession, user_id: int) -> bool:
	"""Удалить пользователя по ID."""
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

	allowed_fields = {
		"enabled_indicators", "entry_conditions",
		"ema_short", "ema_long", "rsi_period",
		"rsi_lower_threshold", "rsi_upper_threshold",
		"atr_period", "macd_fast", "macd_slow", "macd_signal",
		"stochastic_period", "stochastic_lower_threshold", "stochastic_upper_threshold",
		"bollinger_period", "obv_enabled", "volume_period", "vwap_enabled",
		"ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou",
		"sentiment_long_threshold", "sentiment_short_threshold",
		"stop_loss", "take_profit_targets", "take_profit_distribution",
		"trailing_stop", "trailing_mode",
		"allocation_percent", "leverage",
		"strength_multiplier", "enabled"
	}

	for key, value in updates.items():
		if key in allowed_fields and value is not None:
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


# ---------- News ----------
async def create_news(db: AsyncSession, symbol: str, title: str, content: str, source: str, published_at: datetime):
	"""Создать новость и сохранить в БД."""
	try:
		db_news = schemas.NewsORM(
			symbol=symbol,
			title=title,
			content=content,   # ✅ добавлено
			source=source,
			published_at=published_at
		)
		db.add(db_news)
		await db.commit()
		await db.refresh(db_news)
		return db_news
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания новости: {e}")
		raise


async def get_news(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	symbol: str = None,
	source: str = None,
	date_from: datetime = None,
	date_to: datetime = None
):
	"""Получить список новостей с фильтрацией и пагинацией."""
	query = select(schemas.NewsORM)
	if symbol:
		query = query.filter(schemas.NewsORM.symbol == symbol)
	if source:
		query = query.filter(schemas.NewsORM.source == source)
	if date_from:
		query = query.filter(schemas.NewsORM.published_at >= date_from)
	if date_to:
		query = query.filter(schemas.NewsORM.published_at <= date_to)

	query = query.order_by(schemas.NewsORM.published_at.desc())

	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	news = result.scalars().all()

	return {
		"items": news,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}


async def delete_news(db: AsyncSession, news_id: int):
	"""Удалить новость по ID."""
	result = await db.execute(select(schemas.NewsORM).filter(schemas.NewsORM.id == news_id))
	db_news = result.scalars().first()
	if not db_news:
		return None
	await db.delete(db_news)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления новости: {e}")
		raise


async def delete_old_news(db: AsyncSession, days: int = 30):
	"""Удалить новости старше N дней (например, чистка старых записей)"""
	cutoff = datetime.now(timezone.utc) - timedelta(days=days)
	result = await db.execute(
		select(schemas.NewsORM).filter(schemas.NewsORM.published_at < cutoff)
	)
	old_news = result.scalars().all()
	if not old_news:
		return 0
	for n in old_news:
		await db.delete(n)
	try:
		await db.commit()
		return len(old_news)
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления старых новостей: {e}")
		raise


# ---------- ML Models ----------
async def create_ml_model(db: AsyncSession, model_data: dict) -> schemas.MLModelORM:
	"""Создать запись ML модели в БД."""
	try:
		ml_model = schemas.MLModelORM(**model_data)
		db.add(ml_model)
		await db.commit()
		await db.refresh(ml_model)
		return ml_model
	except IntegrityError as e:
		await db.rollback()
		logger.error(f"Ошибка уникальности при создании ML модели: {e}")
		raise
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка БД при создании ML модели: {e}")
		raise

async def get_ml_model_by_name(db: AsyncSession, name: str) -> schemas.MLModelORM | None:
	"""Получить ML модель по имени."""
	result = await db.execute(select(schemas.MLModelORM).filter(schemas.MLModelORM.name == name))
	return result.scalars().first()

async def list_ml_models(db: AsyncSession, skip: int = 0, limit: int = 100):
	"""Список всех ML моделей с пагинацией."""
	query = select(schemas.MLModelORM).offset(skip).limit(limit)
	result = await db.execute(query)
	return result.scalars().all()

async def update_ml_model(db: AsyncSession, model_id: int, updates: dict) -> schemas.MLModelORM | None:
	"""Обновить ML модель по ID."""
	result = await db.execute(select(schemas.MLModelORM).filter(schemas.MLModelORM.id == model_id))
	ml_model = result.scalars().first()
	if not ml_model:
		return None

	allowed_fields = {"name", "type", "path", "params"}
	for key, value in updates.items():
		if key in allowed_fields and value is not None:
			setattr(ml_model, key, value)

	try:
		await db.commit()
		await db.refresh(ml_model)
		return ml_model
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления ML модели: {e}")
		raise

async def delete_ml_model(db: AsyncSession, model_id: int) -> bool:
	"""Удалить ML модель по ID."""
	result = await db.execute(select(schemas.MLModelORM).filter(schemas.MLModelORM.id == model_id))
	ml_model = result.scalars().first()
	if not ml_model:
		return False
	await db.delete(ml_model)
	try:
		await db.commit()
		return True
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка удаления ML модели: {e}")
		raise


# ---------- Risk Settings ----------
async def get_risk_settings(db: AsyncSession) -> schemas.RiskSettingsORM | None:
	"""Получить текущие параметры риска (берём первую запись)."""
	result = await db.execute(select(schemas.RiskSettingsORM).limit(1))
	return result.scalars().first()


async def update_risk_settings(db: AsyncSession, updates: dict) -> schemas.RiskSettingsORM | None:
	"""Обновить параметры риска."""
	result = await db.execute(select(schemas.RiskSettingsORM).limit(1))
	settings_obj = result.scalars().first()

	if not settings_obj:
		# если записи нет — создаём новую
		settings_obj = schemas.RiskSettingsORM(**updates)
		db.add(settings_obj)
	else:
		allowed_fields = {
			"max_risk_per_trade", "max_open_trades", "max_daily_loss", "max_leverage",
			"cooldown_between_trades", "risk_reward_ratio", "dynamic_allocation",
			"commission_rate", "slippage_tolerance", "signal_strength_multiplier", "atr_multiplier"
		}
		for key, value in updates.items():
			if key in allowed_fields and value is not None:
				setattr(settings_obj, key, value)

	try:
		await db.commit()
		await db.refresh(settings_obj)
		return settings_obj
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка обновления risk_settings: {e}")
		return None


# ---------- Risk Logs ----------
async def create_risk_log(db: AsyncSession, log_data: dict) -> schemas.RiskLog:
	"""Создать запись нарушения риск-менеджмента."""
	try:
		risk_log = schemas.RiskLog(
			reason=log_data["reason"],
			symbol=log_data.get("symbol"),
			position_size=log_data.get("position_size"),
			deposit=log_data.get("deposit"),
			sentiment=log_data.get("sentiment"),
			profit_loss=log_data.get("profit_loss"),
			expected_pnl=log_data.get("expected_pnl")
		)
		db.add(risk_log)
		await db.commit()
		await db.refresh(risk_log)
		return risk_log
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"Ошибка создания RiskLog: {e}")
		raise

async def get_risk_logs(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	symbol: str = None,
	reason: str = None,
	date_from: datetime = None,
	date_to: datetime = None,
	sentiment: float = None,
	profit_loss_min: float = None,
	profit_loss_max: float = None
):
	"""Получить список логов риска с фильтрацией и пагинацией."""
	query = select(schemas.RiskLog)
	if symbol:
		query = query.filter(schemas.RiskLog.symbol == symbol)
	if reason:
		query = query.filter(schemas.RiskLog.reason.ilike(f"%{reason}%"))
	if date_from:
		query = query.filter(schemas.RiskLog.timestamp >= date_from)
	if date_to:
		query = query.filter(schemas.RiskLog.timestamp <= date_to)
	if sentiment is not None:
		query = query.filter(schemas.RiskLog.sentiment >= sentiment)
	if profit_loss_min is not None:
		query = query.filter(schemas.RiskLog.profit_loss >= profit_loss_min)
	if profit_loss_max is not None:
		query = query.filter(schemas.RiskLog.profit_loss <= profit_loss_max)

	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	logs = result.scalars().all()

	return {
		"items": logs,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}

async def get_backtest_reports_paginated(
	db: AsyncSession,
	skip: int = 0,
	limit: int = 100,
	symbol: str = None,
	strategy: str = None,
	user_id: int = None,
	date_from: datetime = None,
	date_to: datetime = None
):
	"""Получить отчёты бэктеста с фильтрацией и пагинацией."""
	query = select(schemas.BacktestReport)
	if symbol:
		query = query.filter(schemas.BacktestReport.symbol == symbol)
	if strategy:
		query = query.filter(schemas.BacktestReport.strategy == strategy)
	if user_id:
		query = query.filter(schemas.BacktestReport.user_id == user_id)
	if date_from:
		query = query.filter(schemas.BacktestReport.created_at >= date_from)
	if date_to:
		query = query.filter(schemas.BacktestReport.created_at <= date_to)

	total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
	result = await db.execute(query.offset(skip).limit(limit))
	reports = result.scalars().all()

	return {
		"items": reports,
		"total_count": total_count or 0,
		"page": skip // limit + 1,
		"page_size": limit
	}
