# app/db/session.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from typing import AsyncGenerator

from app.config import settings

logger = logging.getLogger(__name__)

# 🔹 Определяем строки подключения
DATABASE_URL_MAINNET = settings.DATABASE_URL_MAINNET or settings.DATABASE_URL
DATABASE_URL_TESTNET = settings.DATABASE_URL_TESTNET or settings.DATABASE_URL

# 🔹 Создание асинхронных движков
engine_mainnet = create_async_engine(
	DATABASE_URL_MAINNET,
	echo=settings.SQL_ECHO,
	pool_pre_ping=True,
	future=True
)

engine_testnet = create_async_engine(
	DATABASE_URL_TESTNET,
	echo=settings.SQL_ECHO,
	pool_pre_ping=True,
	future=True
)

# 🔹 Фабрики асинхронных сессий
SessionLocal_MAINNET = sessionmaker(
	bind=engine_mainnet,
	class_=AsyncSession,
	expire_on_commit=False,
	autoflush=False,
	autocommit=False
)

SessionLocal_TESTNET = sessionmaker(
	bind=engine_testnet,
	class_=AsyncSession,
	expire_on_commit=False,
	autoflush=False,
	autocommit=False
)

# 🔹 Универсальный алиас для использования в main.py
if settings.USE_TESTNET or settings.ENV == "testnet":
	async_session = SessionLocal_TESTNET
else:
	async_session = SessionLocal_MAINNET

# 🔹 Dependency для FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
	"""Выбор движка в зависимости от окружения (для FastAPI dependency)."""
	if settings.USE_TESTNET or settings.ENV == "testnet":
		session_factory = SessionLocal_TESTNET
	else:
		session_factory = SessionLocal_MAINNET

	async with session_factory() as session:
		try:
			yield session
		except SQLAlchemyError as e:
			logger.error(f"Database error: {e}")
			raise

# 🔹 Универсальный метод для сервисов (например, backtest.py)
async def get_session() -> AsyncGenerator[AsyncSession, None]:
	"""Асинхронная сессия для сервисов (backtest, crud и т.д.)."""
	if settings.USE_TESTNET or settings.ENV == "testnet":
		session_factory = SessionLocal_TESTNET
	else:
		session_factory = SessionLocal_MAINNET

	async with session_factory() as session:
		try:
			yield session
		except SQLAlchemyError as e:
			logger.error(f"Database error: {e}")
			raise
