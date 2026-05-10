# app/api/routes_trades.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

from app.models.trade import Trade
from app.db.session import get_db
from app.db import crud
from app.services.telegram import send_trade_notification
from app.broker.rabbitmq import RabbitMQBroker
from app.cache.redis import RedisCache
from app.utils.logger import logger

router = APIRouter(prefix="/trades", tags=["trades"])

# Инициализация брокеров
rabbitmq = RabbitMQBroker()
redis_cache = RedisCache()

# 🔹 Получить все сделки (с фильтрацией и пагинацией)
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
	db: AsyncSession = Depends(get_db)
):
	try:
		result = await crud.get_trades(
			db,
			skip=skip,
			limit=limit,
			symbol=symbol,
			status=status,
			date_from=date_from,
			date_to=date_to
		)

		# Дополнительная фильтрация по user_id и signal_id
		items = result["items"]
		if user_id:
			items = [t for t in items if t.user_id == user_id]
		if signal_id:
			items = [t for t in items if t.signal_id == signal_id]

		logger.info(f"📊 Получены сделки: {len(items)} шт. (total={result['total_count']})")
		return {
			"items": items,
			"total_count": result["total_count"],
			"page": result["page"],
			"page_size": result["page_size"]
		}
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при получении сделок: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Получить сделку по ID
@router.get("/{trade_id}", response_model=Trade)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	trade = await crud.update_trade(db, trade_id, {})  # просто загрузка без изменений
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"🔎 Получена сделка ID={trade_id}")
	return trade

# 🔹 Добавить новую сделку (с RabbitMQ, Redis и уведомлением в Telegram)
@router.post("/", response_model=Trade)
async def create_trade(trade: Trade, db: AsyncSession = Depends(get_db)):
	try:
		new_trade = await crud.create_trade(db, trade)

		# RabbitMQ публикация
		await rabbitmq.publish_trade(new_trade.dict())
		logger.info(f"📤 Сделка опубликована в RabbitMQ: {new_trade.symbol}")

		# Redis сохранение последней сделки
		await redis_cache.set_json("last_trade", new_trade.dict(), expire=300)
		logger.info(f"💾 Сделка сохранена в Redis: {new_trade.symbol}")

		# Telegram уведомление
		msg = (
			f"💹 Новая сделка: {new_trade.symbol} {new_trade.side} "
			f"по цене {new_trade.price}, статус: {new_trade.status}"
		)
		await send_trade_notification(msg)

		logger.info(f"✅ Сделка создана: {new_trade.symbol} {new_trade.side}")
		return new_trade
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при создании сделки: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить сделку
@router.put("/{trade_id}", response_model=Trade)
async def update_trade(trade_id: int, updated: Trade, db: AsyncSession = Depends(get_db)):
	trade = await crud.update_trade(db, trade_id, updated.dict())
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"✏️ Сделка обновлена ID={trade_id}")
	return trade

# 🔹 Частичное обновление сделки (PATCH)
@router.patch("/{trade_id}", response_model=Trade)
async def patch_trade(trade_id: int, updates: dict, db: AsyncSession = Depends(get_db)):
	trade = await crud.patch_trade(db, trade_id, updates)
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"✏️ Сделка частично обновлена ID={trade_id}")
	return trade

# 🔹 Удалить сделку
@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
	deleted = await crud.delete_trade(db, trade_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Trade not found")
	logger.info(f"🗑️ Сделка удалена ID={trade_id}")
	return {"detail": "Trade deleted"}
