from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class Signal(BaseModel):
	id: Optional[int] = Field(None, description="ID сигнала (генерируется БД)")
	symbol: str = Field(..., description="Торговая пара, например BTC/USDT")
	indicator: str = Field(..., description="Название индикатора, например RSI, EMA, MACD")
	strength: float = Field(..., ge=0, le=1, description="Сила сигнала от 0 до 1")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время генерации сигнала")
	direction: str = Field(..., description="Направление: buy или sell")

	class Config:
		schema_extra = {
			"example": {
					"symbol": "ETH/USDT",
					"indicator": "RSI",
					"strength": 0.85,
					"timestamp": "2026-04-19T18:00:00",
					"direction": "buy"
			}
		}
