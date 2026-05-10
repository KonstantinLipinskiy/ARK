import hashlib
import os
import jwt
from datetime import datetime, timedelta
from app.config import settings

# 🔹 Хэширование пароля с солью
def hash_password(password: str) -> tuple[str, str]:
	"""
	Генерация соли и хэширование пароля.
	Возвращает (salt, password_hash).
	"""
	salt = os.urandom(16).hex()
	password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
	return salt, password_hash

# 🔹 Проверка пароля
def verify_password(password: str, salt: str, stored_hash: str) -> bool:
	"""
	Проверяет введённый пароль против сохранённого хэша.
	"""
	return hashlib.sha256((password + salt).encode()).hexdigest() == stored_hash

# 🔹 Создание JWT access токена
def create_access_token(data: dict, expires_minutes: int = settings.JWT_EXPIRE_MINUTES) -> str:
	"""
	Создаёт JWT access токен.
	data — словарь с данными (например, user_id, role).
	expires_minutes — время жизни токена в минутах.
	"""
	payload = data.copy()
	expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
	payload.update({
		"exp": expire,
		"token_type": "access"
	})
	token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
	return token

# 🔹 Создание JWT refresh токена
def create_refresh_token(data: dict, expires_days: int = settings.JWT_REFRESH_DAYS) -> str:
	"""
	Создаёт JWT refresh токен.
	data — словарь с данными (например, user_id, role).
	expires_days — время жизни токена в днях.
	"""
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
	"""
	Декодирует JWT токен.
	Возвращает payload или None, если токен недействителен/просрочен.
	"""
	try:
		return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
	except jwt.ExpiredSignatureError:
		return None
	except jwt.InvalidTokenError:
		return None
