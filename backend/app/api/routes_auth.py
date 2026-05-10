# app/api/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta
from app.db.session import get_db
from app.db.schemas import UserORM
from app.models.user import UserCreate, UserLogin, UserOut
from app.utils.security import (
	hash_password,
	verify_password,
	create_jwt_token,
	decode_jwt_token
)
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# 🔹 Регистрация нового пользователя
@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(UserORM).where(UserORM.email == user.email))
	existing_user = result.scalar_one_or_none()
	if existing_user:
		logger.error(f"❌ Попытка регистрации с существующим email: {user.email}")
		raise HTTPException(status_code=400, detail="User with this email already exists")

	salt, password_hash = hash_password(user.password)

	new_user = UserORM(
		username=user.username,
		email=user.email,
		role=user.role,
		status="active",
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

# 🔹 Логин пользователя
@router.post("/login")
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(UserORM).where(UserORM.email == credentials.email))
	user = result.scalar_one_or_none()
	if not user or not verify_password(credentials.password, user.salt, user.password_hash):
		logger.error(f"❌ Ошибка входа: неверные данные для {credentials.email}")
		raise HTTPException(status_code=401, detail="Invalid credentials")

	access_token = create_jwt_token(
		{"user_id": user.id, "role": user.role},
		expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	)
	refresh_token = create_jwt_token(
		{"user_id": user.id, "role": user.role},
		expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
	)

	logger.info(f"🔑 Пользователь вошёл: {user.username} ({user.role})")
	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"token_type": "bearer"
	}

# 🔹 Обновление токена (refresh)
@router.post("/refresh")
async def refresh_token(refresh_token: str):
	payload = decode_jwt_token(refresh_token)
	if not payload:
		logger.error("❌ Refresh токен недействителен или истёк")
		raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

	new_access_token = create_jwt_token(
		{"user_id": payload.get("user_id"), "role": payload.get("role")},
		expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	)

	logger.info(f"♻️ Обновлён access токен для user_id={payload.get('user_id')}")
	return {
		"access_token": new_access_token,
		"token_type": "bearer"
	}
