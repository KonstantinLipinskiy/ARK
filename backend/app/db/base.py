# app/db/base.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# --- Асинхронный движок ---
engine = create_async_engine(
	settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
	echo=settings.SQL_ECHO,
	pool_size=settings.DB_POOL_SIZE,
	max_overflow=settings.DB_MAX_OVERFLOW,
	pool_timeout=settings.DB_POOL_TIMEOUT,
	pool_recycle=settings.DB_POOL_RECYCLE,
	pool_pre_ping=True,
	future=True
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
