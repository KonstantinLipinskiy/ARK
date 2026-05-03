from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.signal import Signal
from app.db.schemas import SignalORM
from app.db.session import get_db
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
	db: AsyncSession = Depends(get_db)
):
	query = select(SignalORM)
	if symbol:
		query = query.filter(SignalORM.symbol == symbol)
	if indicator:
		query = query.filter(SignalORM.indicator == indicator)

	result = await db.execute(query.offset(skip).limit(limit))
	signals = result.scalars().all()
	return signals

# 🔹 Получить сигнал по ID
@router.get("/{signal_id}", response_model=Signal)
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(SignalORM).filter(SignalORM.id == signal_id))
	signal = result.scalars().first()
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	return signal

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
		prob = None  # если модель не загружена, сохраняем без фильтрации

	new_signal = SignalORM(**signal.dict(), probability=prob)
	db.add(new_signal)
	try:
		await db.commit()
		await db.refresh(new_signal)
		# Отправляем уведомление в Telegram
		msg = f"📈 Новый сигнал: {new_signal.symbol} {new_signal.direction} ({new_signal.indicator})"
		if prob is not None:
			msg += f" | ML prob={prob:.2f}"
		await send_trade_notification(msg)
		return new_signal
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить сигнал
@router.put("/{signal_id}", response_model=Signal)
async def update_signal(signal_id: int, updated: Signal, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(SignalORM).filter(SignalORM.id == signal_id))
	signal = result.scalars().first()
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")

	for key, value in updated.dict().items():
		setattr(signal, key, value)

	try:
		await db.commit()
		await db.refresh(signal)
		return signal
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Удалить сигнал
@router.delete("/{signal_id}")
async def delete_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(SignalORM).filter(SignalORM.id == signal_id))
	signal = result.scalars().first()
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")

	await db.delete(signal)
	try:
		await db.commit()
		return {"detail": "Signal deleted"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
