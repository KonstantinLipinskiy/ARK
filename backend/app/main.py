from fastapi import FastAPI

# Импортируем конфиг
from app import config

# Импортируем роуты
from app.api import routes_signals, routes_trades, routes_users, routes_admin

# Создаём FastAPI приложение
app = FastAPI(
	title="ARK Trading Bot",
	description="Автоматизированный торговый бот с индикаторами, риск-менеджментом и API",
	version="1.0.0"
)

# Подключаем роуты
app.include_router(routes_signals.router, prefix="/signals", tags=["Signals"])
app.include_router(routes_trades.router, prefix="/trades", tags=["Trades"])
app.include_router(routes_users.router, prefix="/users", tags=["Users"])
app.include_router(routes_admin.router, prefix="/admin", tags=["Admin"])

# Тестовый эндпоинт (для проверки запуска)
@app.get("/")
async def root():
	return {"message": "ARK Bot API is running"}

# Запуск через uvicorn:
# uvicorn app.main:app --reload