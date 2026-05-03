# app/db/base.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import DATABASE_URL

# --- Асинхронный движок ---
engine = create_async_engine(
	DATABASE_URL,
	echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # логирование SQL при отладке
	pool_size=int(os.getenv("DB_POOL_SIZE", 10)),           # размер пула соединений
	max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 20)),     # доп. соединения сверх пула
	pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", 30)),     # таймаут ожидания соединения
	pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 1800))    # время жизни соединения (сек)
)

# --- Фабрика асинхронных сессий ---
SessionLocal = async_sessionmaker(
	autocommit=False,
	autoflush=False,
	bind=engine,
	expire_on_commit=False
)

# --- Декларативная база для ORM моделей ---
Base = declarative_base()
