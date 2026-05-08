from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import time

# Импортируем конфиг
from app import config

# Импортируем роуты
from app.api import routes_signals, routes_trades, routes_users, routes_admin, routes_indicators

# Импортируем сервисы
from app.services.telegram import telegram_service
from app.broker.rabbitmq import init_rabbitmq
from app.cache.redis import init_redis
from app.monitoring import prometheus

# Логирование
from app.utils.logger import logger

# Prometheus метрики для HTTP
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests")
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency in seconds")

# Создаём FastAPI приложение
app = FastAPI(
	title="ARK Trading Bot",
	description="Автоматизированный торговый бот: спот, фьючерсы, ML, динамическая аллокация",
	version="1.0.0"
)

# --- Middleware ---
# CORS
app.add_middleware(
	CORSMiddleware,
	allow_origins=config.settings.ALLOWED_ORIGINS,  # в продакшене ограничить
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# JWT авторизация
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
	try:
		payload = jwt.decode(credentials.credentials, config.settings.JWT_SECRET, algorithms=["HS256"])
		return payload
	except jwt.ExpiredSignatureError:
		raise JSONResponse(status_code=401, content={"error": "Token expired"})
	except jwt.InvalidTokenError:
		raise JSONResponse(status_code=401, content={"error": "Invalid token"})

# Логирование + метрики запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
	logger.info(f"Запрос: {request.method} {request.url}")
	REQUEST_COUNT.inc()  # считаем количество запросов
	start_time = time.time()

	response = await call_next(request)

	duration = time.time() - start_time
	REQUEST_LATENCY.observe(duration)  # фиксируем время ответа
	logger.info(f"Ответ: {response.status_code} за {duration:.4f} сек")
	return response

# --- Централизованное SQL-логирование ---
from sqlalchemy import event
from app.db.session import engine_mainnet, engine_testnet

@event.listens_for(engine_mainnet.sync_engine, "before_cursor_execute")
def before_cursor_execute_mainnet(conn, cursor, statement, parameters, context, executemany):
	logger.info(f"[MAINNET SQL] {statement} | params: {parameters}")

@event.listens_for(engine_testnet.sync_engine, "before_cursor_execute")
def before_cursor_execute_testnet(conn, cursor, statement, parameters, context, executemany):
	logger.info(f"[TESTNET SQL] {statement} | params: {parameters}")

# --- Подключаем роуты ---
app.include_router(routes_signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(routes_trades.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(routes_users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(routes_admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(routes_indicators.router, prefix="/api/v1/indicators", tags=["Indicators"])
app.include_router(prometheus.router)

# --- Системные эндпоинты ---
@app.get("/")
async def root():
	return {"message": "ARK Bot API is running", "mode": config.settings.TRADING_MODE}

from app.broker.rabbitmq import broker
from app.cache.redis import redis_client

@app.get("/health")
async def health_check():
	rabbitmq_ok = broker.connection is not None and not broker.connection.is_closed
	try:
		redis_ok = await redis_client.ping()
	except Exception:
		redis_ok = False

	status = "ok" if rabbitmq_ok and redis_ok else "error"

	return {
		"status": status,
		"rabbitmq": rabbitmq_ok,
		"redis": redis_ok,
		"market_type": config.settings.TRADING_MODE
	}

# --- Инициализация сервисов ---
@app.on_event("startup")
async def startup_event():
	logger.info("Запуск ARK Bot API...")
	await init_rabbitmq()
	await init_redis()
	await telegram_service.send_message("ARK Bot запущен ✅")

@app.on_event("shutdown")
async def shutdown_event():
	logger.info("Остановка ARK Bot API...")
	await telegram_service.send_message("ARK Bot остановлен ❌")

# Запуск через uvicorn:
# uvicorn app.main:app --reload
