# app/api/routes_trades.py
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from app.models.trade import Trade
from app.db.session import get_db
from app.db import crud
from app.services.telegram import send_trade_notification
from app.utils.logger import (
	logger,
	log_order_error,
	log_signal_rejected,
)
from app.utils.security import get_current_user

router = APIRouter(prefix="/trades", tags=["trades"])

@router.get("/")
async def get_trades(
	skip: int = 0,
	limit: int = 50,
	symbol: Optional[str] = Query(None),
	status: Optional[str] = Query(None),
	user_id: Optional[int] = Query(None),
	signal_id: Optional[int] = Query(None),
	date_from: Optional[datetime] = Query(None),
	date_to: Optional[datetime] = Query(None),
	db: AsyncSession = Depends(get_db),
	current_user: dict = Depends(get_current_user)
):
	try:
		result = await crud.get_trades(
			db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			status=status,
			user_id=user_id,
			signal_id=signal_id,
			date_from=date_from,
			date_to=date_to
		)

		logger.info(f"📊 Получены сделки: {len(result['items'])} шт. (total={result['total_count']})")
		return {
			"items": result["items"],
			"total_count": result["total_count"],
			"page": result["page"],
			"page_size": result["page_size"]
		}
	except SQLAlchemyError as e:
		log_order_error("get_trades", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/{trade_id}", response_model=Trade)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
	trade = await crud.get_trade_by_id(db, trade_id)
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"🔎 Получена сделка ID={trade_id}")
	return trade

@router.post("/", response_model=Trade)
async def create_trade(
	trade: Trade,
	request: Request,
	db: AsyncSession = Depends(get_db),
	current_user: dict = Depends(get_current_user)
):
	# ✅ Доступ к RabbitMQ и Redis через app.state
	broker = request.app.state.broker
	redis_client = request.app.state.redis

	try:
		new_trade = await crud.create_trade(db, trade)

		await broker.publish_trade(new_trade.dict())
		logger.info(f"📤 Сделка опубликована в RabbitMQ: {new_trade.symbol}")

		await redis_client.set_json("last_trade", new_trade.dict(), expire=300)
		logger.info(f"💾 Сделка сохранена в Redis: {new_trade.symbol}")

		msg = (
			f"💹 Новая сделка: {new_trade.symbol} {new_trade.side} "
			f"по цене {new_trade.price}, статус: {new_trade.status}"
		)
		await send_trade_notification(msg)

		logger.info(f"✅ Сделка создана: {new_trade.symbol} {new_trade.side}")
		return new_trade
	except SQLAlchemyError as e:
		log_order_error("create_trade", e)
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.put("/{trade_id}", response_model=Trade)
async def update_trade(trade_id: int, updated: Trade, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
	trade = await crud.update_trade(db, trade_id, updated.dict())
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"✏️ Сделка обновлена ID={trade_id}")
	return trade

@router.patch("/{trade_id}", response_model=Trade)
async def patch_trade(trade_id: int, updates: dict, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
	trade = await crud.patch_trade(db, trade_id, updates)
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"✏️ Сделка частично обновлена ID={trade_id}")
	return trade

@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
	deleted = await crud.delete_trade(db, trade_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"🗑️ Сделка удалена ID={trade_id}")
	return {"detail": "Trade deleted"}
