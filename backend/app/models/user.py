from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from typing_extensions import Literal

class User(BaseModel):
	id: Optional[int] = Field(None, description="ID пользователя (генерируется БД)")
	username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
	email: EmailStr = Field(..., description="Email пользователя")
	role: Literal["admin", "trader"] = Field(default="trader", description="Роль пользователя")
	status: Literal["active", "blocked"] = Field(default="active", description="Статус пользователя")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата регистрации")

	# 🔹 Новые поля
	password_hash: Optional[str] = Field(None, description="Хэш пароля для аутентификации")
	salt: Optional[str] = Field(None, description="Соль для хэширования пароля")
	telegram_id: Optional[str] = Field(None, description="Telegram ID для интеграции с ботом")
	last_login: Optional[datetime] = Field(None, description="Дата последнего входа")
	updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Дата последнего обновления")
	settings: Optional[dict] = Field(default_factory=dict, description="Настройки пользователя (например, риск-профиль)")

	class Config:
		json_schema_extra = {
			"example": {
					"username": "konstantin",
					"email": "test@example.com",
					"role": "admin",
					"status": "active",
					"password_hash": "hashed_password_here",
					"salt": "random_salt_here",
					"telegram_id": "123456789",
					"last_login": "2026-05-03T12:00:00",
					"updated_at": "2026-05-03T12:30:00",
					"settings": {"risk_profile": "conservative"}
			}
		}
