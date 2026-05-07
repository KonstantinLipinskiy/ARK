# app/api/routes_signals.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from app.models.signal import Signal
from app.db.session import get_db
from app.db import crud
from app.services.telegram import send_trade_notification
from app.services.ml import MLService

router = APIRouter(prefix="/signals", tags=["signals"])

# Инициализация MLService (модель загружается при старте)
ml_service = MLService()
try:
	ml_service.load_model("models/sklearn_model.pkl", model_type="sklearn")
except Exception:
	ml_service.model = None  # если модель не загружена, фильтрация не работает

# 🔹 Получить все сигналы (с фильтрацией и пагинацией)
@router.get("/", response_model=List[Signal])
async def get_signals(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	indicator: Optional[str] = Query(None),
	user_id: Optional[int] = Query(None),
	trade_id: Optional[int] = Query(None),
	db: AsyncSession = Depends(get_db)
):
	try:
		signals = await crud.get_signals(db, skip=skip, limit=limit, symbol=symbol, indicator=indicator)
		if user_id:
			signals = [s for s in signals if s.user_id == user_id]
		if trade_id:
			signals = [s for s in signals if s.id == trade_id]
		return signals
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Получить сигнал по ID
@router.get("/{signal_id}", response_model=Signal)
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	result = await crud.update_signal(db, signal_id, {})  # просто загрузка без изменений
	if not result:
		raise HTTPException(status_code=404, detail="Signal not found")
	return result

# 🔹 Добавить новый сигнал (с ML‑фильтрацией и уведомлением в Telegram)
@router.post("/", response_model=Signal)
async def create_signal(signal: Signal, db: AsyncSession = Depends(get_db)):
	if signal.direction not in ["buy", "sell"]:
		raise HTTPException(status_code=400, detail="Direction must be 'buy' or 'sell'")

	# формируем признаки для ML
	features = {
		"ema": getattr(signal, "ema", 0.0),
		"rsi": getattr(signal, "rsi", 0.0),
		"macd": getattr(signal, "strength", 0.0),
		"hour": signal.timestamp.hour if signal.timestamp else 0,
		"atr": getattr(signal, "atr", 0.0)
	}

	# фильтрация слабых сигналов
	if ml_service.model:
		try:
			prob = ml_service.predict_signal(features)
		except Exception as e:
			raise HTTPException(status_code=500, detail=f"Ошибка ML при прогнозе: {e}")

		if prob < 0.6:
			raise HTTPException(status_code=400, detail=f"Сигнал отфильтрован как слабый (prob={prob:.2f})")
	else:
		prob = None

	try:
		new_signal = await crud.create_signal(db, signal)
		# добавляем вероятность в объект
		if prob is not None:
			new_signal.confidence = prob
		# Отправляем уведомление в Telegram
		msg = f"📈 Новый сигнал: {new_signal.symbol} {new_signal.direction} ({new_signal.indicator})"
		if prob is not None:
			msg += f" | ML prob={prob:.2f}"
		await send_trade_notification(msg)
		return new_signal
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить сигнал
@router.put("/{signal_id}", response_model=Signal)
async def update_signal(signal_id: int, updated: Signal, db: AsyncSession = Depends(get_db)):
	signal = await crud.update_signal(db, signal_id, updated.dict())
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	return signal

# 🔹 Удалить сигнал
@router.delete("/{signal_id}")
async def delete_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	deleted = await crud.delete_signal(db, signal_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Signal not found")
	return {"detail": "Signal deleted"}
