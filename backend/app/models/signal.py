# app/models/signal.py
from pydantic import BaseModel, Field, validator
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
	ATR = "ATR"
	OBV = "OBV"
	Stochastic = "Stochastic"
	Volume = "Volume"
	VWAP = "VWAP"
	Ichimoku = "Ichimoku"


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

	# 🔹 Валидаторы
	@validator("timestamp")
	def validate_timestamp(cls, v: datetime) -> datetime:
		"""Проверка, что timestamp не в будущем."""
		if v > datetime.utcnow():
			raise ValueError("timestamp не может быть в будущем")
		return v

	@validator("strength")
	def validate_strength(cls, v: float) -> float:
		"""Проверка диапазона strength."""
		if not (0 <= v <= 1):
			raise ValueError("strength должен быть в диапазоне [0,1]")
		return v

	@validator("confidence")
	def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
		"""Проверка диапазона confidence."""
		if v is not None and not (0 <= v <= 1):
			raise ValueError("confidence должен быть в диапазоне [0,1]")
		return v

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
