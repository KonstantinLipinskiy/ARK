import asyncio
import logging
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from alembic import context
from app.db import schemas  # убедись, что здесь импортированы все ORM модели

# -------------------------------------------------------------------
# Логирование Alembic
# -------------------------------------------------------------------
fileConfig(context.config.config_file_name)
logging.basicConfig(
	format="%(asctime)s [%(levelname)s] %(message)s",
	level=logging.INFO
)
logger = logging.getLogger("alembic.env")

# -------------------------------------------------------------------
# Выбор окружения (testnet / mainnet)
# -------------------------------------------------------------------
DATABASE_URL = (
	os.getenv("DATABASE_URL_TESTNET")
	if os.getenv("USE_TESTNET") == "true"
	else os.getenv("DATABASE_URL")
)

# -------------------------------------------------------------------
# Создание движка и фабрики сессий
# -------------------------------------------------------------------
try:
	connectable = create_async_engine(DATABASE_URL, echo=True, future=True)
	async_session_factory = sessionmaker(
		bind=connectable,
		class_=AsyncSession,
		expire_on_commit=False
	)
	logger.info("Успешное подключение к БД")
except Exception as e:
	logger.error(f"Ошибка подключения к БД: {e}")
	raise

# -------------------------------------------------------------------
# Метаданные моделей
# -------------------------------------------------------------------
target_metadata = schemas.Base.metadata

# -------------------------------------------------------------------
# Запуск миграций
# -------------------------------------------------------------------
def run_migrations_offline():
	"""Запуск миграций в offline-режиме (без подключения к БД)."""
	url = DATABASE_URL
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)
	with context.begin_transaction():
		context.run_migrations()


def run_migrations_online():
	"""Запуск миграций в online-режиме (с подключением к БД)."""
	async def do_run_migrations():
		async with connectable.connect() as connection:
			await connection.run_sync(
					lambda sync_conn: context.configure(
						connection=sync_conn,
						target_metadata=target_metadata,
						compare_type=True,
						compare_server_default=True,
					)
			)
			async with connection.begin():
					context.run_migrations()

	asyncio.run(do_run_migrations())


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
