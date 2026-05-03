from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from typing_extensions import Literal

class Trade(BaseModel):
	id: Optional[int] = Field(None, description="ID сделки (генерируется БД)")
	symbol: str = Field(..., description="Торговая пара, например BTC/USDT")
	side: Literal["buy", "sell"] = Field(..., description="Направление сделки: buy или sell")
	amount: float = Field(..., gt=0, description="Количество актива")
	price: float = Field(..., gt=0, description="Цена исполнения")
	timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время сделки")
	status: Literal["open", "closed", "cancelled"] = Field(default="open", description="Статус сделки")

	# 🔹 Новые аналитические поля
	entry_price: Optional[float] = Field(None, gt=0, description="Цена входа")
	exit_price: Optional[float] = Field(None, gt=0, description="Цена выхода")
	profit_loss: Optional[float] = Field(None, description="PnL сделки")
	leverage: Optional[float] = Field(1.0, gt=0, description="Плечо сделки")

	# 🔹 Связи
	user_id: Optional[int] = Field(None, description="ID пользователя, которому принадлежит сделка")
	signal_id: Optional[int] = Field(None, description="ID сигнала, породившего сделку")

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
					"user_id": 1,
					"signal_id": 101
			}
		}
