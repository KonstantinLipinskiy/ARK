from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from typing_extensions import Literal
import enum

# Enum для индикаторов
class IndicatorEnum(str, enum.Enum):
	RSI = "RSI"
	EMA = "EMA"
	MACD = "MACD"
	Bollinger = "Bollinger"

class Signal(BaseModel):
	id: Optional[int] = Field(None, description="ID сигнала (генерируется БД)")
	symbol: str = Field(..., description="Торговая пара, например BTC/USDT")
	indicator: IndicatorEnum = Field(..., description="Название индикатора")
	strength: float = Field(..., ge=0, le=1, description="Сила сигнала от 0 до 1")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время генерации сигнала")
	direction: Literal["buy", "sell"] = Field(..., description="Направление: buy или sell")

	# 🔹 Новые поля
	user_id: Optional[int] = Field(None, description="ID пользователя, для которого сигнал")
	trade_id: Optional[int] = Field(None, description="ID сделки, связанной с сигналом")
	confidence: Optional[float] = Field(None, ge=0, le=1, description="Доверие к сигналу")
	source: Optional[str] = Field(None, description="Источник сигнала (стратегия или внешний сервис)")

	class Config:
		json_schema_extra = {
			"example": {
					"symbol": "ETH/USDT",
					"indicator": "RSI",
					"strength": 0.85,
					"timestamp": "2026-04-19T18:00:00",
					"direction": "buy",
					"user_id": 1,
					"trade_id": 42,
					"confidence": 0.9,
					"source": "EMA+RSI strategy"
			}
		}
