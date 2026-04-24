import os
import sys
import os

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Импортируем Base и все ORM‑модели
from app.db.base import Base
from app.db import schemas


# Загружаем конфиг Alembic
config = context.config

# Читаем DATABASE_URL из .env
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./arkbot.db")
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Логирование
if config.config_file_name is not None:
	fileConfig(config.config_file_name)

# Метаданные моделей (нужны Alembic для автогенерации миграций)
target_metadata = Base.metadata

def run_migrations_offline():
	"""Запуск миграций в оффлайн-режиме (без подключения к БД)."""
	url = config.get_main_option("sqlalchemy.url")
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)

	with context.begin_transaction():
		context.run_migrations()

def run_migrations_online():
	"""Запуск миграций в онлайн-режиме (с подключением к БД)."""
	connectable = engine_from_config(
		config.get_section(config.config_ini_section),
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)

	with connectable.connect() as connection:
		context.configure(
			connection=connection,
			target_metadata=target_metadata
		)

		with context.begin_transaction():
			context.run_migrations()

# Определяем режим запуска
if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
