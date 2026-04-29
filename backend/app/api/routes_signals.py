# app/api/routes_signals.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.signal import Signal
from app.db.schemas import SignalORM
from app.db.session import get_db
from app.services.telegram import send_trade_notification

router = APIRouter(prefix="/signals", tags=["signals"])

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

# 🔹 Добавить новый сигнал (с валидацией и уведомлением в Telegram)
@router.post("/", response_model=Signal)
async def create_signal(signal: Signal, db: AsyncSession = Depends(get_db)):
	if signal.direction not in ["buy", "sell"]:
		raise HTTPException(status_code=400, detail="Direction must be 'buy' or 'sell'")

	new_signal = SignalORM(**signal.dict())
	db.add(new_signal)
	try:
		await db.commit()
		await db.refresh(new_signal)
		# Отправляем уведомление в Telegram
		await send_trade_notification(f"📈 Новый сигнал: {new_signal.symbol} {new_signal.direction} ({new_signal.indicator})")
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
