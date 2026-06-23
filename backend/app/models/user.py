#app/models/user.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict
from datetime import datetime, timezone
from typing_extensions import Literal


class User(BaseModel):
	id: Optional[int] = Field(None, description="ID пользователя (генерируется БД)")
	username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
	email: EmailStr = Field(..., description="Email пользователя")
	role: Literal["admin", "trader"] = Field(default="trader", description="Роль пользователя")
	status: Literal["active", "blocked"] = Field(default="active", description="Статус пользователя")
	created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Дата регистрации")

	password_hash: str = Field(..., description="Хэш пароля для аутентификации")
	salt: str = Field(..., description="Соль для хэширования пароля")
	telegram_id: Optional[str] = Field(None, description="Telegram ID для интеграции с ботом")
	is_admin: bool = Field(default=False, description="Флаг администратора")
	last_login: Optional[datetime] = Field(None, description="Дата последнего входа")
	updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Дата последнего обновления")
	settings: Optional[Dict] = Field(
		default_factory=dict,
		description="Настройки пользователя (например, risk_profile и notifications_enabled)"
	)

	class Config:
		json_schema_extra = {
			"example": {
				"id": 1,
				"username": "konstantin",
				"email": "test@example.com",
				"role": "admin",
				"status": "active",
				"password_hash": "hashed_password_here",
				"salt": "random_salt_here",
				"telegram_id": "123456789",
				"is_admin": True,
				"last_login": "2026-05-03T12:00:00",
				"updated_at": "2026-05-03T12:30:00",
				"settings": {
					"risk_profile": "conservative",
					"notifications_enabled": True
				}
			}
		}


class UserCreate(BaseModel):
	username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
	email: EmailStr = Field(..., description="Email пользователя")
	password: str = Field(..., min_length=6, description="Пароль пользователя")
	role: Literal["admin", "trader"] = Field(default="trader", description="Роль пользователя")
	telegram_id: Optional[str] = Field(None, description="Telegram ID для интеграции с ботом")
	is_admin: bool = Field(default=False, description="Флаг администратора")
	settings: Optional[Dict] = Field(
		default_factory=dict,
		description="Настройки пользователя (например, risk_profile, notifications_enabled)"
	)

	class Config:
		json_schema_extra = {
			"example": {
				"username": "new_user",
				"email": "new@example.com",
				"password": "secure_password",
				"role": "trader",
				"telegram_id": "987654321",
				"is_admin": False,
				"settings": {
					"risk_profile": "moderate",
					"notifications_enabled": False
				}
			}
		}


class UserLogin(BaseModel):
	email: EmailStr = Field(..., description="Email пользователя")
	password: str = Field(..., min_length=6, description="Пароль пользователя")

	class Config:
		json_schema_extra = {
			"example": {
				"email": "test@example.com",
				"password": "secure_password"
			}
		}


class UserOut(BaseModel):
	id: int
	username: str
	email: EmailStr
	role: str
	status: str
	created_at: datetime
	last_login: Optional[datetime]
	updated_at: datetime
	telegram_id: Optional[str]
	is_admin: bool
	settings: Optional[Dict]

	class Config:
		orm_mode = True
		json_schema_extra = {
			"example": {
				"id": 1,
				"username": "konstantin",
				"email": "test@example.com",
				"role": "admin",
				"status": "active",
				"created_at": "2026-05-07T12:00:00",
				"last_login": "2026-05-07T12:30:00",
				"updated_at": "2026-05-07T12:45:00",
				"telegram_id": "123456789",
				"is_admin": True,
				"settings": {
					"risk_profile": "aggressive",
					"notifications_enabled": True
				}
			}
		}


class UserUpdate(BaseModel):
	username: Optional[str] = Field(None, min_length=3, max_length=50, description="Имя пользователя")
	email: Optional[EmailStr] = Field(None, description="Email пользователя")
	role: Optional[Literal["admin", "trader"]] = Field(None, description="Роль пользователя")
	status: Optional[Literal["active", "blocked"]] = Field(None, description="Статус пользователя")
	telegram_id: Optional[str] = Field(None, description="Telegram ID для интеграции с ботом")
	is_admin: Optional[bool] = Field(None, description="Флаг администратора")
	settings: Optional[Dict] = Field(
		default=None,
		description="Настройки пользователя (например, risk_profile, notifications_enabled)"
	)

	class Config:
		json_schema_extra = {
			"example": {
				"username": "updated_user",
				"email": "updated@example.com",
				"role": "trader",
				"status": "active",
				"telegram_id": "987654321",
				"is_admin": False,
				"settings": {
					"risk_profile": "moderate",
					"notifications_enabled": True
				}
			}
		}
