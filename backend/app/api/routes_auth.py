from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from app.db.session import get_db
from app.db.schemas import UserORM, UserStatus, UserRole
from app.models.user import UserCreate, UserLogin, UserOut
from app.utils.security import (
	hash_password,
	verify_password,
	create_access_token,
	create_refresh_token,
	decode_jwt_token
)
from app.utils.logger import (
	logger,
	log_order_error,
	log_risk_violation,
)
from app.db import crud
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(UserORM).where(UserORM.email == user.email))
	existing_user = result.scalar_one_or_none()
	if existing_user:
		log_order_error("register", Exception(f"Попытка регистрации с существующим email: {user.email}"))
		raise HTTPException(status_code=400, detail="User with this email already exists")

	salt, password_hash = hash_password(user.password)

	new_user = UserORM(
		username=user.username,
		email=user.email,
		role=UserRole(user.role) if isinstance(user.role, str) else user.role,
		status=UserStatus.active,
		password_hash=password_hash,
		salt=salt,
		telegram_id=user.telegram_id,
		settings=user.settings
	)
	db.add(new_user)
	await db.commit()
	await db.refresh(new_user)

	logger.info(f"✅ Новый пользователь зарегистрирован: {new_user.username} ({new_user.role})")
	return new_user

@router.post("/login")
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(UserORM).where(UserORM.email == credentials.email))
	user = result.scalar_one_or_none()
	if not user or not verify_password(credentials.password, user.salt, user.password_hash):
		log_order_error("login", Exception(f"Неверные данные для {credentials.email}"))
		raise HTTPException(status_code=401, detail="Invalid credentials")

	if user.status != UserStatus.active:
		log_risk_violation(user.email, "Попытка входа заблокированного пользователя")
		raise HTTPException(status_code=403, detail="User is blocked")

	access_token = create_access_token(
		{"user_id": user.id, "role": user.role.value},
		expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
	)
	refresh_token = create_refresh_token(
		{"user_id": user.id, "role": user.role.value},
		expires_days=REFRESH_TOKEN_EXPIRE_DAYS
	)

	expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
	await crud.create_refresh_token(db, user.id, refresh_token, expires_at)

	logger.info(f"🔑 Пользователь вошёл: {user.username} ({user.role})")
	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"token_type": "bearer"
	}

@router.post("/refresh")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
	payload = decode_jwt_token(refresh_token)
	if not payload:
		log_risk_violation("refresh_token", "Попытка обновления с недействительным refresh токеном")
		raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

	db_token = await crud.get_refresh_token(db, refresh_token)
	if not db_token or db_token.expires_at < datetime.utcnow():
		log_risk_violation("refresh_token", "Refresh токен отсутствует в БД или истёк")
		raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

	new_access_token = create_access_token(
		{"user_id": payload.get("user_id"), "role": payload.get("role")},
		expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
	)

	logger.info(f"♻️ Обновлён access токен для user_id={payload.get('user_id')}")
	return {
		"access_token": new_access_token,
		"token_type": "bearer"
	}

@router.post("/logout")
async def logout(user_id: int, db: AsyncSession = Depends(get_db)):
	success = await crud.delete_tokens_by_user(db, user_id)
	if not success:
		log_risk_violation(user_id, "Попытка logout: токены пользователя не найдены")
		raise HTTPException(status_code=404, detail="No refresh tokens found for user")
	logger.info(f"🚪 Пользователь {user_id} вышел, refresh токены удалены")
	return {"detail": "User logged out, refresh tokens revoked"}
