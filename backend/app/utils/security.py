# app/utils/security.py
import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from app.config import settings
from app.utils.logger import logger

# 🔹 Настройка bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# 🔹 Хэширование пароля
def hash_password(password: str) -> str:
	"""
	Хэширование пароля с использованием bcrypt.
	"""
	return pwd_context.hash(password)

# 🔹 Проверка пароля
def verify_password(password: str, hashed_password: str) -> bool:
	"""
	Проверяет введённый пароль против сохранённого хэша.
	"""
	return pwd_context.verify(password, hashed_password)

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
		logger.warning("⚠️ JWT токен просрочен")
		return None
	except jwt.InvalidTokenError as e:
		logger.error(f"❌ Невалидный JWT токен: {e}")
		return None

# 🔹 Получение текущего пользователя
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
	token = credentials.credentials
	payload = decode_jwt_token(token)
	if not payload:
		logger.warning("❌ Unauthorized access attempt (invalid/expired token)")
		raise HTTPException(status_code=401, detail="Unauthorized")

	user_id = payload.get("user_id")
	role = payload.get("role")

	if not user_id or not role:
		logger.warning("❌ Unauthorized access attempt (no user_id/role in token)")
		raise HTTPException(status_code=401, detail="Unauthorized")

	return {"user_id": user_id, "role": role}

# 🔹 Получение текущего администратора
async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
	token = credentials.credentials
	payload = decode_jwt_token(token)
	if not payload:
		logger.warning("❌ Unauthorized admin access attempt (invalid/expired token)")
		raise HTTPException(status_code=401, detail="Unauthorized")

	user_id = payload.get("user_id")
	role = payload.get("role")

	if not user_id or not role:
		logger.warning("❌ Unauthorized admin access attempt (no user_id/role in token)")
		raise HTTPException(status_code=401, detail="Unauthorized")

	if role != "admin":
		logger.error(f"🚫 User {user_id} with role '{role}' tried to access admin endpoint")
		raise HTTPException(status_code=403, detail="Admin privileges required")

	logger.info(f"✅ Admin {user_id} успешно получил доступ")
	return {"user_id": user_id, "role": role}
