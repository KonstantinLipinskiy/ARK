from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import time
from app import config
from app.api import routes_signals, routes_trades, routes_users, routes_admin, routes_indicators
from app.services.telegram import telegram_service
from app.broker.rabbitmq import init_rabbitmq, broker
from app.cache.redis import init_redis, redis_client
from app.monitoring import prometheus
from app.utils.logger import logger
from prometheus_client import Counter, Histogram
from sqlalchemy import event
from app.db.session import engine_mainnet, engine_testnet, async_session
from app.services.risk import RiskService   # ✅ импорт RiskService

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests")
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency in seconds")

app = FastAPI(
	title="ARK Trading Bot",
	description="Автоматизированный торговый бот: спот, фьючерсы, ML, динамическая аллокация",
	version="1.0.0"
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=config.settings.ALLOWED_ORIGINS,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
	try:
		payload = jwt.decode(credentials.credentials, config.settings.JWT_SECRET, algorithms=["HS256"])
		return payload
	except jwt.ExpiredSignatureError:
		raise HTTPException(status_code=401, detail="Token expired")
	except jwt.InvalidTokenError:
		raise HTTPException(status_code=401, detail="Invalid token")

@app.middleware("http")
async def log_requests(request: Request, call_next):
	logger.info(f"Запрос: {request.method} {request.url}")
	REQUEST_COUNT.inc()
	start_time = time.time()

	response = await call_next(request)

	duration = time.time() - start_time
	REQUEST_LATENCY.observe(duration) 
	logger.info(f"Ответ: {response.status_code} за {duration:.4f} сек")
	return response

@event.listens_for(engine_mainnet.sync_engine, "before_cursor_execute")
def before_cursor_execute_mainnet(conn, cursor, statement, parameters, context, executemany):
	logger.info(f"[MAINNET SQL] {statement} | params: {parameters}")

@event.listens_for(engine_testnet.sync_engine, "before_cursor_execute")
def before_cursor_execute_testnet(conn, cursor, statement, parameters, context, executemany):
	logger.info(f"[TESTNET SQL] {statement} | params: {parameters}")

app.include_router(routes_signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(routes_trades.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(routes_users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(routes_admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(routes_indicators.router, prefix="/api/v1/indicators", tags=["Indicators"])
app.include_router(prometheus.router)

@app.get("/")
async def root():
	return {"message": "ARK Bot API is running", "mode": config.settings.TRADING_MODE}

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



@app.get("/risk-check")
async def risk_check(request: Request):
	risk_service: RiskService = request.app.state.risk_service
	return {
		"config_loaded": bool(risk_service.STRATEGY_CONFIG),
		"risk_config_keys": list(risk_service.RISK_CONFIG.keys())
	}


@app.on_event("startup")
async def startup_event():
	logger.info("Запуск ARK Bot API...")
	await init_rabbitmq()
	await init_redis()

	# ✅ создаём RiskService и явно подтягиваем конфиги
	async with async_session() as db_session:
		app.state.risk_service = RiskService(db_session)
		await app.state.risk_service.refresh_config()

	await telegram_service.send_message("ARK Bot запущен ✅")

@app.on_event("shutdown")
async def shutdown_event():
	logger.info("Остановка ARK Bot API...")
	await telegram_service.send_message("ARK Bot остановлен ❌")
