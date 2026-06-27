# app/utils/security.py
import os
import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.config import settings
from app.utils.logger import logger
from app.db.session import get_db
from app.db.schemas import UserORM
from app.models.user import UserOut

# 🔹 Настройка bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# 🔹 Хэширование пароля с солью
def hash_password(password: str) -> tuple[str, str]:
	"""
	Возвращает (salt, password_hash).
	salt генерируется случайно, password_hash считается как bcrypt-хэш от password+salt.
	"""
	salt = os.urandom(16).hex()
	password_hash = pwd_context.hash(password + salt)
	return salt, password_hash

# 🔹 Проверка пароля
def verify_password(password: str, salt: str, hashed_password: str) -> bool:
	"""
	Проверяет введённый пароль против сохранённого хэша с солью.
	"""
	return pwd_context.verify(password + salt, hashed_password)

# 🔹 Создание JWT access токена
def create_access_token(data: dict, expires_minutes: int = settings.JWT_EXPIRE_MINUTES) -> str:
	payload = data.copy()
	expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
	payload.update({
		"exp": expire,
		"token_type": "access"
	})
	token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
	return token

# 🔹 Создание JWT refresh токена
def create_refresh_token(data: dict, expires_days: int = settings.REFRESH_TOKEN_EXPIRE_DAYS) -> str:
	payload = data.copy()
	expire = datetime.utcnow() + timedelta(days=expires_days)
	payload.update({
		"exp": expire,
		"token_type": "refresh"
	})
	token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
	return token

# 🔹 Декодирование JWT токена
def decode_jwt_token(token: str) -> dict | None:
	try:
		return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
	except jwt.ExpiredSignatureError:
		logger.warning("⚠️ JWT токен просрочен",
						extra={"operation": "security", "collection": "jwt"})
		return None
	except jwt.InvalidTokenError as e:
		logger.error(f"❌ Невалидный JWT токен: {e}",
						extra={"operation": "security", "collection": "jwt"})
		return None

# 🔹 Получение текущего пользователя


async def get_current_user(
	credentials: HTTPAuthorizationCredentials = Depends(security),
	db: AsyncSession = Depends(get_db)
	) -> UserOut:
	token = credentials.credentials
	payload = decode_jwt_token(token)
	if not payload:
		logger.warning("❌ Unauthorized access attempt (invalid/expired token)",
						extra={"operation": "security", "collection": "auth"})
		raise HTTPException(status_code=401, detail="Unauthorized")

	user_id = payload.get("user_id")
	role = payload.get("role")

	if not user_id or not role:
		logger.warning("❌ Unauthorized access attempt (no user_id/role in token)",
						extra={"operation": "security", "collection": "auth"})
		raise HTTPException(status_code=401, detail="Unauthorized")

	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")

	return UserOut.model_validate(user)


# 🔹 Получение текущего администратора
async def get_current_admin(
	credentials: HTTPAuthorizationCredentials = Depends(security),
	db: AsyncSession = Depends(get_db)
	) -> UserORM:
	token = credentials.credentials
	payload = decode_jwt_token(token)
	if not payload:
		logger.warning("❌ Unauthorized admin access attempt (invalid/expired token)",
						extra={"operation": "security", "collection": "auth"})
		raise HTTPException(status_code=401, detail="Unauthorized")

	user_id = payload.get("user_id")
	role = payload.get("role")

	if not user_id or not role:
		logger.warning("❌ Unauthorized admin access attempt (no user_id/role in token)",
						extra={"operation": "security", "collection": "auth"})
		raise HTTPException(status_code=401, detail="Unauthorized")

	if role != "admin":
		logger.error(f"🚫 User {user_id} with role '{role}' tried to access admin endpoint",
						extra={"operation": "security", "collection": "auth"})
		raise HTTPException(status_code=403, detail="Admin privileges required")

	result = await db.execute(select(UserORM).filter(UserORM.id == user_id))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")

	logger.info(f"✅ Admin {user_id} успешно получил доступ",
				extra={"operation": "security", "collection": "auth"})
	return user
