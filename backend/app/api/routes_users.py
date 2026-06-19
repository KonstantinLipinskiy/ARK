#app/api/routes_users.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app.models.user import UserOut, UserCreate, User
from app.db.schemas import UserORM
from app.db.session import get_db
from app.services.telegram import telegram_service
from app.utils.security import hash_password, get_current_user
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
		query = select(UserORM)
		if username:
			query = query.filter(UserORM.username.ilike(f"%{username}%"))
		if role:
			query = query.filter(UserORM.role == role)

		total_count = await db.scalar(select(func.count()).select_from(query.subquery()))
		result = await db.execute(query.offset(skip).limit(limit))
		users = result.scalars().all()

		logger.info(f"📊 Получены пользователи: {len(users)} шт. (total={total_count})")
		return {
			"items": users,
			"total_count": total_count or 0,
			"page": skip // limit + 1,
			"page_size": limit
		}
	except SQLAlchemyError as e:
		logger.error(f"❌ Ошибка БД при получении пользователей: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
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

	salt, password_hash = hash_password(user.password)

	settings = user.settings or {}
	if "notifications_enabled" not in settings:
		settings["notifications_enabled"] = True

	new_user = UserORM(
		username=user.username,
		email=user.email,
		role=user.role,
		status="active",
		password_hash=password_hash,
		salt=salt,
		telegram_id=user.telegram_id,
		settings=settings
	)
	db.add(new_user)
	try:
		await db.commit()
		await db.refresh(new_user)
		if new_user.telegram_id and new_user.settings.get("notifications_enabled", True):
			await telegram_service.send_message_to_user(new_user, f"👤 Новый пользователь: {new_user.username} (роль: {new_user.role})")
		logger.info(f"✅ Пользователь создан: {new_user.username} ({new_user.role})")
		return new_user
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"❌ Ошибка БД при создании пользователя: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.put("/{user_id}", response_model=UserOut)
async def update_user(
	user_id: int,
	updated: UserOut,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		logger.error(f"❌ Пользователь ID={user_id} не найден для обновления")
		raise HTTPException(status_code=404, detail="User not found")

	if current_user.role != "admin" and current_user.id != user_id:
		raise HTTPException(status_code=403, detail="Not enough permissions")

	for key, value in updated.dict(exclude_unset=True).items():
		if key == "settings" and value:
			user.settings.update(value)
		else:
			setattr(user, key, value)

	try:
		await db.commit()
		await db.refresh(user)
		logger.info(f"✏️ Пользователь обновлён ID={user_id}")
		return user
	except SQLAlchemyError as e:
		await db.rollback()
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

	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		logger.error(f"❌ Пользователь ID={user_id} не найден для удаления")
		raise HTTPException(status_code=404, detail="User not found")

	await db.delete(user)
	try:
		await db.commit()
		logger.info(f"🗑️ Пользователь удалён ID={user_id}")
		return {"detail": "User deleted"}
	except SQLAlchemyError as e:
		await db.rollback()
		logger.error(f"❌ Ошибка БД при удалении пользователя: {e}")
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
