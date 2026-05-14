import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(
	settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"), 
	echo=os.getenv("SQL_ECHO", "false").lower() == "true",
	pool_size=int(os.getenv("DB_POOL_SIZE", 10)),
	max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 20)),
	pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", 30)),
	pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 1800)),
	pool_pre_ping=True,
	future=True
)

SessionLocal = async_sessionmaker(
	autocommit=False,
	autoflush=False,
	bind=engine,
	expire_on_commit=False
)

Base = declarative_base()
