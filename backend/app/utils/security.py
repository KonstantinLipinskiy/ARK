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

# 🔹 Создание JWT токена
def create_jwt_token(data: dict, expires_delta: int = settings.JWT_EXPIRE_MINUTES) -> str:
	"""
	Создаёт JWT токен.
	data — словарь с данными (например, user_id, role).
	expires_delta — время жизни токена в минутах.
	"""
	payload = data.copy()
	payload.update({"exp": datetime.utcnow() + timedelta(minutes=expires_delta)})
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
