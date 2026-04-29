# app/api/routes_users.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.user import User
from app.db.schemas import UserORM
from app.db.session import get_db
from app.services.telegram import send_trade_notification
from app.utils.auth import get_current_user  # JWT проверка

router = APIRouter(prefix="/users", tags=["users"])

# 🔹 Получить всех пользователей (с фильтрацией и пагинацией)
@router.get("/", response_model=List[User])
async def get_users(
	skip: int = 0,
	limit: int = 50,
	name: Optional[str] = Query(None),
	role: Optional[str] = Query(None),
	db: AsyncSession = Depends(get_db),
	current_user: User = Depends(get_current_user)  # проверка токена
):
	query = select(UserORM)
	if name:
		query = query.filter(UserORM.name.ilike(f"%{name}%"))
	if role:
		query = query.filter(UserORM.role == role)

	result = await db.execute(query.offset(skip).limit(limit))
	users = result.scalars().all()
	return users

# 🔹 Получить пользователя по ID
@router.get("/{user_id}", response_model=User)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	return user

# 🔹 Добавить нового пользователя
@router.post("/", response_model=User)
async def create_user(user: User, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
	new_user = UserORM(**user.dict())
	db.add(new_user)
	try:
		await db.commit()
		await db.refresh(new_user)
		# Отправляем уведомление в Telegram (если указан telegram_id)
		if new_user.telegram_id:
			await send_trade_notification(f"👤 Новый пользователь: {new_user.name} (роль: {new_user.role})")
		return new_user
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить пользователя
@router.put("/{user_id}", response_model=User)
async def update_user(user_id: int, updated: User, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")

	for key, value in updated.dict().items():
		setattr(user, key, value)

	try:
		await db.commit()
		await db.refresh(user)
		return user
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Удалить пользователя
@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")

	await db.delete(user)
	try:
		await db.commit()
		return {"detail": "User deleted"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
