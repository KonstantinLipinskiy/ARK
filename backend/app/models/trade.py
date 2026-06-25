#app/models/trade.py
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional
from typing_extensions import Literal

class Trade(BaseModel):
	id: Optional[int] = Field(None, description="ID сделки (генерируется БД)")
	symbol: str = Field(..., description="Торговая пара, например BTC/USDT")
	side: Literal["buy", "sell"] = Field(..., description="Направление сделки: buy или sell")
	amount: float = Field(..., gt=0, description="Количество актива")
	price: float = Field(..., gt=0, description="Цена исполнения")
	timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Время сделки")
	status: Literal["open", "closed", "cancelled"] = Field(default="open", description="Статус сделки")
	entry_price: Optional[float] = Field(None, gt=0, description="Цена входа")
	exit_price: Optional[float] = Field(None, gt=0, description="Цена выхода")
	profit_loss: Optional[float] = Field(None, description="PnL сделки")
	leverage: Optional[float] = Field(1.0, gt=0, description="Плечо сделки")
	stop_loss: Optional[float] = Field(None, description="Стоп-лосс %")
	take_profit: Optional[float] = Field(None, description="Тейк-профит %")
	confidence_score: Optional[float] = Field(None, description="Доверие ML модели")
	risk_reason: Optional[str] = Field(None, description="Причина отказа при валидации риска")
	exchange_order_id: Optional[str] = Field(None, description="ID ордера на бирже")
	user_id: Optional[int] = Field(None, description="ID пользователя, которому принадлежит сделка")
	signal_id: Optional[int] = Field(None, description="ID сигнала, породившего сделку")
	news_sentiment: Optional[float] = Field(None, description="Средний sentiment новостей, связанных с активом")


	class Config:
		json_schema_extra = {
			"example": {
					"symbol": "BTC/USDT",
					"side": "buy",
					"amount": 0.01,
					"price": 30000.0,
					"status": "open",
					"entry_price": 29950.0,
					"exit_price": 30500.0,
					"profit_loss": 55.0,
					"leverage": 5,
					"stop_loss": 2.5,
					"take_profit": 5.0,
					"confidence_score": 0.87,
					"risk_reason": "Risk check failed: leverage too high",
					"exchange_order_id": "BYBIT123456789",
					"user_id": 1,
					"signal_id": 101,
					"news_sentiment": -0.12
			}
		}
