from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

# 🔹 Получить общую статистику бота
@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
	stats = {
		"total_trades": db.execute("SELECT COUNT(*) FROM trades").scalar(),
		"active_signals": db.execute("SELECT COUNT(*) FROM signals WHERE status='active'").scalar(),
		"users": db.execute("SELECT COUNT(*) FROM users").scalar(),
	}
	return stats

# 🔹 Управление пользователями (например, блокировка)
@router.post("/block_user/{user_id}")
def block_user(user_id: int, db: Session = Depends(get_db)):
	user = db.execute(f"SELECT * FROM users WHERE id={user_id}").fetchone()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	db.execute(f"UPDATE users SET status='blocked' WHERE id={user_id}")
	db.commit()
	return {"detail": f"User {user_id} blocked"}

# 🔹 Управление стратегиями (например, включение/выключение)
@router.post("/toggle_strategy/{pair}")
def toggle_strategy(pair: str, db: Session = Depends(get_db)):
	# Здесь можно обновить конфиг стратегий в БД
	return {"detail": f"Strategy for {pair} toggled"}
