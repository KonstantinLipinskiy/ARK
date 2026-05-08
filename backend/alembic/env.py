from logging.config import fileConfig
import os
import sys
from dotenv import load_dotenv

from sqlalchemy import engine_from_config, pool
from alembic import context

# Добавляем корень проекта (backend) в sys.path,
# чтобы Alembic видел пакет app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Импортируем базу и модели
from app.db.base import Base
from app.db import schemas  # если у тебя все модели собираются здесь

# Загружаем переменные окружения
load_dotenv()

# Alembic Config object
config = context.config

# Устанавливаем URL подключения из .env
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
	config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Настройка логирования
if config.config_file_name is not None:
	fileConfig(config.config_file_name)

# Метаданные моделей для автогенерации
target_metadata = Base.metadata


def run_migrations_offline() -> None:
	"""Run migrations in 'offline' mode."""
	url = config.get_main_option("sqlalchemy.url")
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)

	with context.begin_transaction():
		context.run_migrations()


def run_migrations_online() -> None:
	"""Run migrations in 'online' mode."""
	connectable = engine_from_config(
		config.get_section(config.config_ini_section, {}),
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)

	with connectable.connect() as connection:
		context.configure(connection=connection, target_metadata=target_metadata)

		with context.begin_transaction():
			context.run_migrations()


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
