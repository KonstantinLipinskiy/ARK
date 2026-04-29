# app/db/session.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings

logger = logging.getLogger(__name__)

# 🔹 Определяем строку подключения
DATABASE_URL = settings.DATABASE_URL

# 🔹 Создание асинхронного движка PostgreSQL
engine = create_async_engine(
	DATABASE_URL,
	echo=settings.SQL_ECHO,
	pool_pre_ping=True,
	future=True
)

# 🔹 Фабрика асинхронных сессий
SessionLocal = sessionmaker(
	bind=engine,
	class_=AsyncSession,
	expire_on_commit=False,
	autoflush=False,
	autocommit=False
)

# 🔹 Dependency для FastAPI
async def get_db() -> AsyncSession:
	async with SessionLocal() as session:
		try:
			yield session
		except SQLAlchemyError as e:
			logger.error(f"Database error: {e}")
			raise
