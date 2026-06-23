# app/api/routes_signals.py
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from app.models.signal import Signal
from app.db.session import get_db
from app.db import crud
from app.services.telegram import send_trade_notification
from app.services.ml import MLService
from app.services.news_loader import NewsLoader
from app.utils.logger import (
	logger,
	log_order_error,
	log_signal_rejected,
)
from app.config import settings
from app.utils.security import get_current_user

router = APIRouter(prefix="/signals", tags=["signals"])

# --- ML Service ---
ml_service = MLService()
try:
	ml_service.load_model(settings.MODEL_PATH, model_type=settings.MODEL_TYPE)
except Exception:
	ml_service.model = None

# --- News Loader ---
news_loader = NewsLoader(newsdata_api_key=settings.NEWSDATA_API_KEY)

@router.get("/")
async def get_signals(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	indicator: Optional[str] = Query(None),
	user_id: Optional[int] = Query(None),
	trade_id: Optional[int] = Query(None),
	date_from: Optional[datetime] = Query(None),
	date_to: Optional[datetime] = Query(None),
	db: AsyncSession = Depends(get_db)
):
	try:
		result = await crud.get_signals(
			db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			indicator=indicator,
			user_id=user_id,
			trade_id=trade_id,
			date_from=date_from,
			date_to=date_to
		)
		logger.info(f"📊 Получены сигналы: {len(result['items'])} шт. (total={result['total_count']})")
		return result
	except SQLAlchemyError as e:
		log_order_error("get_signals", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/{signal_id}", response_model=Signal)
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	result = await crud.get_signal_by_id(db, signal_id)
	if not result:
		raise HTTPException(status_code=404, detail="Signal not found")
	logger.info(f"🔎 Получен сигнал ID={signal_id}")
	return result

@router.post("/", response_model=Signal)
async def create_signal(
	signal: Signal,
	request: Request,
	db: AsyncSession = Depends(get_db),
	current_user: dict = Depends(get_current_user)
):
	# ✅ Доступ к RabbitMQ и Redis через app.state
	broker = request.app.state.broker
	redis_client = request.app.state.redis

	if signal.direction not in ["buy", "sell"]:
		raise HTTPException(status_code=400, detail="Direction must be 'buy' or 'sell'")

	features = {
		"ema": getattr(signal, "ema", 0.0),
		"rsi": getattr(signal, "rsi", 0.0),
		"macd": getattr(signal, "strength", 0.0),
		"hour": signal.timestamp.hour if signal.timestamp else 0,
		"atr": getattr(signal, "atr", 0.0),
		"obv": getattr(signal, "obv", 0.0),
		"stochastic": getattr(signal, "stochastic", 0.0),
		"vwap": getattr(signal, "vwap", 0.0),
		"ichimoku": getattr(signal, "ichimoku", 0.0),
		"volume": getattr(signal, "volume", 0.0),
		"volume_ma": getattr(signal, "volume_ma", 0.0),
		"bollinger": getattr(signal, "bollinger", 0.0),
		"bollinger_upper": getattr(signal, "bollinger_upper", 0.0),
		"bollinger_lower": getattr(signal, "bollinger_lower", 0.0),
		"last_price": getattr(signal, "last_price", 0.0),
		"spread": getattr(signal, "spread", 0.0),
		"liquidity_imbalance": getattr(signal, "liquidity_imbalance", 0.0),
		"mark_price": getattr(signal, "mark_price", 0.0),
		"user_id": current_user["user_id"]
	}

	# 🔹 Подтягиваем свежие новости и считаем sentiment
	try:
		latest_news = news_loader.fetch_newsdata(query=signal.symbol.split("/")[0].lower())
		if latest_news:
			df_news = ml_service.prepare_data([{"news": text} for text in latest_news])
			features["news_sentiment"] = df_news["news_sentiment"].mean()
		else:
			features["news_sentiment"] = 0.0
	except Exception as e:
		log_order_error("news_loader", e)
		features["news_sentiment"] = 0.0

	# ML фильтрация
	if ml_service.model:
		try:
			prob = ml_service.predict_signal(features)
		except Exception as e:
			log_order_error("ml_predict", e)
			raise HTTPException(status_code=500, detail=f"Ошибка ML при прогнозе: {e}")

		if prob < settings.CONFIDENCE_THRESHOLD:
			log_signal_rejected(signal.symbol, prob)
			raise HTTPException(status_code=400, detail=f"Сигнал отфильтрован как слабый (prob={prob:.2f})")
	else:
		prob = None

	try:
		new_signal = await crud.create_signal(db, signal)
		if prob is not None:
			new_signal.confidence = prob

		await broker.publish_signal(new_signal.dict())
		logger.info(f"📤 Сигнал опубликован в RabbitMQ: {new_signal.symbol}")

		await redis_client.set_json("last_signal", new_signal.dict(), expire=300)
		logger.info(f"💾 Сигнал сохранён в Redis: {new_signal.symbol}")

		msg = f"📈 Новый сигнал: {new_signal.symbol} {new_signal.direction} ({new_signal.indicator})"
		if prob is not None:
			msg += f" | ML prob={prob:.2f}"
		await send_trade_notification(msg)

		logger.info(f"✅ Сигнал создан: {new_signal.symbol} {new_signal.direction}")
		return new_signal
	except SQLAlchemyError as e:
		log_order_error("create_signal", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.put("/{signal_id}", response_model=Signal)
async def update_signal(signal_id: int, updated: Signal, db: AsyncSession = Depends(get_db)):
	signal = await crud.update_signal(db, signal_id, updated.dict())
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	logger.info(f"✏️ Сигнал обновлён ID={signal_id}")
	return signal

@router.patch("/{signal_id}", response_model=Signal)
async def patch_signal(signal_id: int, updates: dict, db: AsyncSession = Depends(get_db)):
	signal = await crud.patch_signal(db, signal_id, updates)
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	logger.info(f"✏️ Сигнал частично обновлён ID={signal_id}")
	return signal

@router.delete("/{signal_id}")
async def delete_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	deleted = await crud.delete_signal(db, signal_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Signal not found")
	logger.info(f"🗑️ Сигнал удалён ID={signal_id}")
	return {"detail": "Signal deleted"}
