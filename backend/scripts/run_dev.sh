#!/bin/bash
# run_dev.sh — запуск проекта в dev-режиме

# Загружаем переменные окружения из .env
export $(grep -v '^#' .env | xargs)

# Папка проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🚀 Запуск ARK Trading Bot в dev-режиме..."
echo "📂 Проект: $PROJECT_DIR"
echo "🌍 ENV=$ENV | DB=$DATABASE_URL"

# 1. Запуск Alembic миграций
echo "🔄 Применяем миграции Alembic..."
alembic upgrade head

# 2. Запуск FastAPI (uvicorn)
echo "🌐 Запускаем FastAPI сервер..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &

# 3. Запуск Celery воркера
echo "⚙️ Запускаем Celery worker..."
celery -A app.tasks worker --loglevel=INFO &

# 4. Запуск Celery beat (расписание задач)
echo "⏰ Запускаем Celery beat..."
celery -A app.celery_app beat --loglevel=INFO &

# 5. Логирование
echo "📜 Логи пишутся в папку: $LOG_DIR"

# Ждём завершения процессов
wait
