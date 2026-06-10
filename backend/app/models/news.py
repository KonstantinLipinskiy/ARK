from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class NewsBase(BaseModel):
	symbol: str
	title: str
	content: str
	source: Optional[str] = None
	published_at: Optional[datetime] = None

class NewsCreate(NewsBase):
	"""Схема для создания новости (POST)."""
	pass

class NewsRead(NewsBase):
	"""Схема для чтения новости (GET)."""
	id: int

	class Config:
		orm_mode = True
