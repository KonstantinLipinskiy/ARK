# app/api/routes_trades.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from app.models.trade import Trade
from app.db.session import get_db
from app.db import crud
from app.services.telegram import send_trade_notification

router = APIRouter(prefix="/trades", tags=["trades"])

# 🔹 Получить все сделки (с фильтрацией и пагинацией)
@router.get("/", response_model=List[Trade])
async def get_trades(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	status: Optional[str] = Query(None),
	user_id: Optional[int] = Query(None),
	signal_id: Optional[int] = Query(None),
	date_from: Optional[datetime] = Query(None),
	date_to: Optional[datetime] = Query(None),
	db: AsyncSession = Depends(get_db)
):
	try:
		# базовый запрос
		trades = await crud.get_trades(db, skip=skip, limit=limit, symbol=symbol, status=status)

		# фильтрация по user_id и signal_id
		if user_id:
			trades = [t for t in trades if t.user_id == user_id]
		if signal_id:
			trades = [t for t in trades if t.signal_id == signal_id]
		if date_from:
			trades = [t for t in trades if t.timestamp >= date_from]
		if date_to:
			trades = [t for t in trades if t.timestamp <= date_to]

		return trades
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Получить сделку по ID
@router.get("/{trade_id}", response_model=Trade)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	trade = await crud.update_trade(db, trade_id, {})  # просто загрузка без изменений
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	return trade

# 🔹 Добавить новую сделку (с уведомлением в Telegram)
@router.post("/", response_model=Trade)
async def create_trade(trade: Trade, db: AsyncSession = Depends(get_db)):
	try:
		new_trade = await crud.create_trade(db, trade)
		# Отправляем уведомление в Telegram
		await send_trade_notification(
			f"💹 Новая сделка: {new_trade.symbol} {new_trade.side} "
			f"по цене {new_trade.price}, статус: {new_trade.status}"
		)
		return new_trade
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить сделку
@router.put("/{trade_id}", response_model=Trade)
async def update_trade(trade_id: int, updated: Trade, db: AsyncSession = Depends(get_db)):
	trade = await crud.update_trade(db, trade_id, updated.dict())
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	return trade

# 🔹 Удалить сделку
@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	deleted = await crud.delete_trade(db, trade_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Trade not found")
	return {"detail": "Trade deleted"}
