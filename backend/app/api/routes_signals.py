from fastapi import APIRouter, HTTPException, Depends
from typing import List
from sqlalchemy.orm import Session
from app.models import Signal
from app.db.schemas import SignalORM
from app.db.session import get_db

router = APIRouter(prefix="/signals", tags=["signals"])

# 🔹 Получить все сигналы
@router.get("/", response_model=List[Signal])
def get_signals(db: Session = Depends(get_db)):
	signals = db.query(SignalORM).all()
	return signals

# 🔹 Получить сигнал по ID
@router.get("/{signal_id}", response_model=Signal)
def get_signal(signal_id: int, db: Session = Depends(get_db)):
	signal = db.query(SignalORM).filter(SignalORM.id == signal_id).first()
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	return signal

# 🔹 Добавить новый сигнал
@router.post("/", response_model=Signal)
def create_signal(signal: Signal, db: Session = Depends(get_db)):
	new_signal = SignalORM(**signal.dict())
	db.add(new_signal)
	db.commit()
	db.refresh(new_signal)
	return new_signal

# 🔹 Удалить сигнал
@router.delete("/{signal_id}")
def delete_signal(signal_id: int, db: Session = Depends(get_db)):
	signal = db.query(SignalORM).filter(SignalORM.id == signal_id).first()
	if not signal:
		raise HTTPException(status_code=404, detail="Signal not found")
	db.delete(signal)
	db.commit()
	return {"detail": "Signal deleted"}
