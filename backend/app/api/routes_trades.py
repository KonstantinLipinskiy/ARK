from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.trade import Trade
from app.db.schemas import TradeORM
from app.db.session import get_db
from app.services.telegram import send_trade_notification
from datetime import datetime

router = APIRouter(prefix="/trades", tags=["trades"])

# 🔹 Получить все сделки (с фильтрацией и пагинацией)
@router.get("/", response_model=List[Trade])
async def get_trades(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	status: Optional[str] = Query(None),
	date_from: Optional[datetime] = Query(None),
	date_to: Optional[datetime] = Query(None),
	is_backtest: Optional[bool] = Query(False),
	db: AsyncSession = Depends(get_db)
):
	query = select(TradeORM).filter(TradeORM.is_backtest == is_backtest)

	if symbol:
		query = query.filter(TradeORM.symbol == symbol)
	if status:
		query = query.filter(TradeORM.status == status)
	if date_from:
		query = query.filter(TradeORM.timestamp >= date_from)
	if date_to:
		query = query.filter(TradeORM.timestamp <= date_to)

	result = await db.execute(query.offset(skip).limit(limit))
	trades = result.scalars().all()
	return trades

# 🔹 Получить сделку по ID
@router.get("/{trade_id}", response_model=Trade)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(TradeORM).filter(TradeORM.id == trade_id))
	trade = result.scalars().first()
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	return trade

# 🔹 Добавить новую сделку (с уведомлением в Telegram)
@router.post("/", response_model=Trade)
async def create_trade(trade: Trade, db: AsyncSession = Depends(get_db)):
	new_trade = TradeORM(**trade.dict())
	db.add(new_trade)
	try:
		await db.commit()
		await db.refresh(new_trade)
		# Отправляем уведомление в Telegram
		await send_trade_notification(
			f"💹 Новая сделка: {new_trade.symbol} {new_trade.side} "
			f"по цене {new_trade.price}, статус: {new_trade.status}"
		)
		return new_trade
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить сделку
@router.put("/{trade_id}", response_model=Trade)
async def update_trade(trade_id: int, updated: Trade, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(TradeORM).filter(TradeORM.id == trade_id))
	trade = result.scalars().first()
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")

	for key, value in updated.dict().items():
		setattr(trade, key, value)

	try:
		await db.commit()
		await db.refresh(trade)
		return trade
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Удалить сделку
@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(TradeORM).filter(TradeORM.id == trade_id))
	trade = result.scalars().first()
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")

	await db.delete(trade)
	try:
		await db.commit()
		return {"detail": "Trade deleted"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
