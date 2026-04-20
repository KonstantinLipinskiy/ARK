# app/api/routes_trades.py
from fastapi import APIRouter, HTTPException
from typing import List
from app.models import Trade  # Pydantic модель
from app.db.schemas import TradeORM  # SQLAlchemy модель
from app.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/trades", tags=["trades"])

# 🔹 Получить все сделки
@router.get("/", response_model=List[Trade])
def get_trades(db: Session = get_db()):
	trades = db.query(TradeORM).all()
	return trades

# 🔹 Получить сделку по ID
@router.get("/{trade_id}", response_model=Trade)
def get_trade(trade_id: int, db: Session = get_db()):
	trade = db.query(TradeORM).filter(TradeORM.id == trade_id).first()
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	return trade

# 🔹 Добавить новую сделку
@router.post("/", response_model=Trade)
def create_trade(trade: Trade, db: Session = get_db()):
	new_trade = TradeORM(**trade.dict())
	db.add(new_trade)
	db.commit()
	db.refresh(new_trade)
	return new_trade

# 🔹 Удалить сделку
@router.delete("/{trade_id}")
def delete_trade(trade_id: int, db: Session = get_db()):
	trade = db.query(TradeORM).filter(TradeORM.id == trade_id).first()
	if not trade:
		raise HTTPException(status_code=404, detail="Trade not found")
	db.delete(trade)
	db.commit()
	return {"detail": "Trade deleted"}
