# app/api/routes_admin.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import get_db
from app.db.schemas import UserORM, TradeORM, SignalORM
from app.services.telegram import send_trade_notification
from app.utils.auth import get_current_admin  # проверка JWT и роли admin
from sqlalchemy import func

router = APIRouter(prefix="/admin", tags=["admin"])

# 🔹 Получить общую статистику бота
@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	try:
		total_trades = await db.scalar(select(func.count()).select_from(TradeORM))
		active_signals = await db.scalar(select(func.count()).select_from(SignalORM).filter(SignalORM.status == "active"))
		users = await db.scalar(select(func.count()).select_from(UserORM))

		# Дополнительно: winrate и средний профит
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
		await send_trade_notification(f"🚫 Пользователь {user.name} (ID: {user_id}) был заблокирован админом.")
		return {"detail": f"User {user_id} blocked"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Управление стратегиями (например, включение/выключение)
@router.post("/toggle_strategy/{pair}")
async def toggle_strategy(pair: str, db: AsyncSession = Depends(get_db), current_admin: UserORM = Depends(get_current_admin)):
	# Здесь можно обновить конфиг стратегий в БД
	try:
		# Пример: обновляем статус стратегии
		await send_trade_notification(f"⚙️ Стратегия для {pair} была изменена админом.")
		return {"detail": f"Strategy for {pair} toggled"}
	except SQLAlchemyError as e:
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
