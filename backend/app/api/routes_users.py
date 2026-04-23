from fastapi import APIRouter, HTTPException, Depends
from typing import List
from sqlalchemy.orm import Session
from app.models import User
from app.db.schemas import UserORM
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])

# 🔹 Получить всех пользователей
@router.get("/", response_model=List[User])
def get_users(db: Session = Depends(get_db)):
	users = db.query(UserORM).all()
	return users

# 🔹 Получить пользователя по ID
@router.get("/{user_id}", response_model=User)
def get_user(user_id: int, db: Session = Depends(get_db)):
	user = db.query(UserORM).filter(UserORM.id == user_id).first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	return user

# 🔹 Добавить нового пользователя
@router.post("/", response_model=User)
def create_user(user: User, db: Session = Depends(get_db)):
	new_user = UserORM(**user.dict())
	db.add(new_user)
	db.commit()
	db.refresh(new_user)
	return new_user

# 🔹 Удалить пользователя
@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
	user = db.query(UserORM).filter(UserORM.id == user_id).first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	db.delete(user)
	db.commit()
	return {"detail": "User deleted"}
