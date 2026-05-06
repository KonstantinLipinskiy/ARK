# app/api/routes_admin.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app.db.session import get_db
from app.db.schemas import UserORM, TradeORM, SignalORM, StrategyORM
from app.services.strategy_service import load_strategies, add_strategy, update_strategy, delete_strategy
from app.services.risk_service import load_risk_settings, update_risk_settings
from app.utils.auth import get_current_admin  # проверка JWT и роли admin

router = APIRouter(prefix="/admin", tags=["admin"])

# 🔹 Получить общую статистику бота
@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	try:
		total_trades = await db.scalar(select(func.count()).select_from(TradeORM))
		active_signals = await db.scalar(select(func.count()).select_from(SignalORM).filter(SignalORM.status == "active"))
		users = await db.scalar(select(func.count()).select_from(UserORM))

		wins = await db.scalar(select(func.count()).select_from(TradeORM).filter(TradeORM.profit > 0))
		avg_profit = await db.scalar(select(func.avg(TradeORM.profit)))
		active_positions = await db.scalar(select(func.count()).select_from(TradeORM).filter(TradeORM.status == "open"))

		stats = {
			"total_trades": total_trades,
			"active_signals": active_signals,
			"users": users,
			"winrate": round((wins / total_trades) * 100, 2) if total_trades else 0,
			"avg_profit": avg_profit or 0,
			"active_positions": active_positions
		}
		return stats
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Управление пользователями (например, блокировка)
@router.post("/block_user/{user_id}")
async def block_user(user_id: int, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")

	user.status = "blocked"
	try:
		await db.commit()
		return {"detail": f"User {user_id} blocked"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Получить список стратегий
@router.get("/strategies")
async def get_strategies(db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	return await load_strategies(db, use_cache=False)

# 🔹 Добавить стратегию
@router.post("/strategies")
async def create_strategy(strategy_data: dict, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	strategy = await add_strategy(db, strategy_data)
	if not strategy:
		raise HTTPException(status_code=400, detail="Failed to add strategy")
	return {"detail": f"Strategy {strategy.symbol} added"}

# 🔹 Обновить стратегию
@router.put("/strategies/{symbol}")
async def edit_strategy(symbol: str, updates: dict, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	strategy = await update_strategy(db, symbol, updates)
	if not strategy:
		raise HTTPException(status_code=404, detail="Strategy not found")
	return {"detail": f"Strategy {symbol} updated"}

# 🔹 Удалить стратегию
@router.delete("/strategies/{symbol}")
async def remove_strategy(symbol: str, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	success = await delete_strategy(db, symbol)
	if not success:
		raise HTTPException(status_code=404, detail="Strategy not found")
	return {"detail": f"Strategy {symbol} deleted"}

# 🔹 Получить текущие параметры риска (из БД)
@router.get("/risk")
async def get_risk(db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	return await load_risk_settings(db)

# 🔹 Обновить параметры риска (в БД)
@router.put("/risk")
async def update_risk(updates: dict, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	new_config = await update_risk_settings(db, updates)
	if not new_config:
		raise HTTPException(status_code=400, detail="Risk update failed")
	return {"detail": "Risk config updated", "config": new_config}
