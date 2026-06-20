#!/bin/bash
# run_prod.sh — запуск проекта в prod-режиме

# Загружаем переменные окружения из .env
export $(grep -v '^#' .env | xargs)

# Папка проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🚀 Запуск ARK Trading Bot в PROD-режиме..."
echo "📂 Проект: $PROJECT_DIR"
echo "🌍 ENV=$ENV | DB=$DATABASE_URL"

# 1. Применяем миграции Alembic
echo "🔄 Применяем миграции Alembic..."
alembic upgrade head

# 2. Запуск FastAPI через gunicorn (uvicorn workers)
echo "🌐 Запускаем FastAPI сервер (gunicorn + uvicorn)..."
gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --log-level info &

# 3. Запуск Celery worker
echo "⚙️ Запускаем Celery worker..."
celery -A app.tasks worker --loglevel=INFO --concurrency=4 &

# 4. Запуск Celery beat (расписание задач)
echo "⏰ Запускаем Celery beat..."
celery -A app.celery_app beat --loglevel=INFO &

# 5. Логирование
echo "📜 Логи пишутся в папку: $LOG_DIR"

# Ждём завершения процессов
wait
