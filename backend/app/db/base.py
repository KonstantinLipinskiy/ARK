from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL


# URL подключения к БД (пока можно оставить SQLite для тестов)
SQLALCHEMY_DATABASE_URL = "sqlite:///./arkbot.db"
# Для PostgreSQL будет так:
# SQLALCHEMY_DATABASE_URL = DATABASE_URL

# Создаём движок
engine = create_engine(
	SQLALCHEMY_DATABASE_URL,
	connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}
)

# Создаём фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Декларативная база для ORM‑моделей
Base = declarative_base()
