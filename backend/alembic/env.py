import os
import sys
from logging.config import fileConfig
from dotenv import load_dotenv

from sqlalchemy import create_engine, pool
from alembic import context

# -------------------------------------------------------------------
# Загружаем переменные окружения
# -------------------------------------------------------------------
load_dotenv()

# Alembic Config object
config = context.config

# Логирование
if config.config_file_name is not None:
	fileConfig(config.config_file_name)

# -------------------------------------------------------------------
# Добавляем путь к корню проекта
# -------------------------------------------------------------------
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Импортируем базу и модели
from app.db import schemas  # убедись, что здесь импортированы все ORM модели
target_metadata = schemas.Base.metadata

# -------------------------------------------------------------------
# Строка подключения
# -------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
	raise RuntimeError("DATABASE_URL не найден в .env")

# Alembic работает только с sync‑движком → заменяем asyncpg на psycopg2
SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

# -------------------------------------------------------------------
# Offline migrations
# -------------------------------------------------------------------
def run_migrations_offline() -> None:
	"""Запуск миграций в offline‑режиме (без подключения к БД)."""
	url = config.get_main_option("sqlalchemy.url")
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)
	with context.begin_transaction():
		context.run_migrations()

# -------------------------------------------------------------------
# Online migrations
# -------------------------------------------------------------------
def run_migrations_online() -> None:
	"""Запуск миграций в online‑режиме (с подключением к БД)."""
	connectable = create_engine(
		config.get_main_option("sqlalchemy.url"),
		poolclass=pool.NullPool,
		future=True,
		echo=True,
	)
	with connectable.connect() as connection:
		context.configure(
			connection=connection,
			target_metadata=target_metadata,
			compare_type=True,
			compare_server_default=True,
		)
		with context.begin_transaction():
			context.run_migrations()

# -------------------------------------------------------------------
# Запуск
# -------------------------------------------------------------------
if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
