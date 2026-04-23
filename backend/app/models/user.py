from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime

class User(BaseModel):
	id: Optional[int] = Field(None, description="ID пользователя (генерируется БД)")
	username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
	email: EmailStr = Field(..., description="Email пользователя")
	role: str = Field(default="trader", description="Роль пользователя: admin или trader")
	created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата регистрации")

	class Config:
		json_schema_extra = {
			"example": {
					"username": "konstantin",
					"email": "test@example.com",
					"role": "admin"
			}
		}
