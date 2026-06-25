#app/models/news.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NewsBase(BaseModel):
	symbol: str
	title: str
	content: Optional[str] = None   # ⚡ теперь опционально, как в ORM (nullable=True)
	source: Optional[str] = None
	published_at: datetime          # ⚡ обязательное поле, как в ORM (nullable=False)

class NewsCreate(NewsBase):
	"""Схема для создания новости (POST)."""
	pass

class NewsUpdate(BaseModel):
	"""Схема для обновления новости (PUT/PATCH)."""
	symbol: Optional[str] = None
	title: Optional[str] = None
	content: Optional[str] = None
	source: Optional[str] = None
	published_at: Optional[datetime] = None

	class Config:
		orm_mode = True

class NewsRead(NewsBase):
	"""Схема для чтения новости (GET)."""
	id: int
	created_at: datetime            # ⚡ добавлено для синхронности с ORM

	class Config:
		orm_mode = True
