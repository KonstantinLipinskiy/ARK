from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class Trade(BaseModel):
	id: Optional[int] = Field(None, description="ID сделки (генерируется БД)")
	symbol: str = Field(..., description="Торговая пара, например BTC/USDT")
	side: str = Field(..., description="Направление сделки: buy или sell")
	amount: float = Field(..., gt=0, description="Количество актива")
	price: float = Field(..., gt=0, description="Цена исполнения")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время сделки")
	status: str = Field(default="open", description="Статус сделки: open, closed, cancelled")

	class Config:
		schema_extra = {
			"example": {
					"symbol": "BTC/USDT",
					"side": "buy",
					"amount": 0.01,
					"price": 30000.0,
					"status": "open"
			}
		}
