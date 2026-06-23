# app/api/routes_users.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app.models.user import UserOut, UserCreate, UserUpdate
from app.db.session import get_db
from app.db import crud
from app.services.telegram import telegram_service
from app.utils.security import get_current_user
from app.utils.logger import logger

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/")
async def get_users(
	skip: int = 0,
	limit: int = 50,
	username: Optional[str] = Query(None),
	role: Optional[str] = Query(None),
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	try:
		result = await crud.get_users(db, skip=skip, limit=limit, username=username, role=role)
		logger.info(f"📊 Получены пользователи: {len(result['items'])} шт. (total={result['total_count']})")
		return result
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при получении пользователей: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	user = await crud.get_user_by_id(db, user_id)
	if not user:
		logger.error(f"❌ Пользователь ID={user_id} не найден")
		raise HTTPException(status_code=404, detail="User not found")
	logger.info(f"🔎 Получен пользователь ID={user_id}")
	return user


@router.post("/", response_model=UserOut)
async def create_user(
	user: UserCreate,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	if current_user.role != "admin":
		raise HTTPException(status_code=403, detail="Only admin can create users")

	try:
		new_user = await crud.create_user(db, user)
		if new_user.telegram_id and new_user.settings.get("notifications_enabled", True):
			await telegram_service.send_message_to_user(
				new_user,
				f"👤 Новый пользователь: {new_user.username} (роль: {new_user.role})"
			)
		logger.info(f"✅ Пользователь создан: {new_user.username} ({new_user.role})")
		return new_user
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при создании пользователя: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
	user_id: int,
	updated: UserUpdate,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	# проверка прав
	if current_user.role != "admin" and current_user.id != user_id:
		raise HTTPException(status_code=403, detail="Not enough permissions")

	try:
		user = await crud.update_user(db, user_id, updated)
		if not user:
			logger.error(f"❌ Пользователь ID={user_id} не найден для обновления")
			raise HTTPException(status_code=404, detail="User not found")
		logger.info(f"✏️ Пользователь обновлён ID={user_id}")
		return user
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при обновлении пользователя: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.delete("/{user_id}")
async def delete_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	if current_user.role != "admin":
		raise HTTPException(status_code=403, detail="Only admin can delete users")

	try:
		deleted = await crud.delete_user(db, user_id)
		if not deleted:
			logger.error(f"❌ Пользователь ID={user_id} не найден для удаления")
			raise HTTPException(status_code=404, detail="User not found")
		logger.info(f"🗑️ Пользователь удалён ID={user_id}")
		return {"detail": "User deleted"}
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при удалении пользователя: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
