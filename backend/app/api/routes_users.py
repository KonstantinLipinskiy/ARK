from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.user import UserOut, UserCreate, User
from app.db.schemas import UserORM
from app.db.session import get_db
from app.services.telegram import telegram_service
from app.utils.auth import get_current_user
from app.utils.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

# 🔹 Получить всех пользователей
@router.get("/", response_model=List[UserOut])
async def get_users(
	skip: int = 0,
	limit: int = 50,
	username: Optional[str] = Query(None),
	role: Optional[str] = Query(None),
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	query = select(UserORM)
	if username:
		query = query.filter(UserORM.username.ilike(f"%{username}%"))
	if role:
		query = query.filter(UserORM.role == role)

	result = await db.execute(query.offset(skip).limit(limit))
	return result.scalars().all()

# 🔹 Получить пользователя по ID
@router.get("/{user_id}", response_model=UserOut)
async def get_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	return user

# 🔹 Добавить нового пользователя (только admin)
@router.post("/", response_model=UserOut)
async def create_user(
	user: UserCreate,
	db: AsyncSession = Depends(get_db),
	current_user: UserOut = Depends(get_current_user)
):
	if current_user.role != "admin":
		raise HTTPException(status_code=403, detail="Only admin can create users")

	salt, password_hash = hash_password(user.password)

	# 🔹 notifications_enabled по умолчанию True
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
			await telegram_service.send_message(
					f"👤 Новый пользователь: {new_user.username} (роль: {new_user.role})"
			)
		return new_user
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Обновить пользователя (admin или сам пользователь)
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
		raise HTTPException(status_code=404, detail="User not found")

	if current_user.role != "admin" and current_user.id != user_id:
		raise HTTPException(status_code=403, detail="Not enough permissions")

	for key, value in updated.dict(exclude_unset=True).items():
		if key == "settings" and value:
			# 🔹 обновляем notifications_enabled
			user.settings.update(value)
		else:
			setattr(user, key, value)

	try:
		await db.commit()
		await db.refresh(user)
		return user
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")

# 🔹 Удалить пользователя (только admin)
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
		raise HTTPException(status_code=404, detail="User not found")

	await db.delete(user)
	try:
		await db.commit()
		return {"detail": "User deleted"}
	except SQLAlchemyError as e:
		await db.rollback()
		raise HTTPException(status_code=500, detail=f"Database error: {e}")
