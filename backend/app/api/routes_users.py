# app/api/routes_users.py
from fastapi import APIRouter, HTTPException
from typing import List
from app.models import User  # Pydantic модель
from app.db.schemas import UserORM  # SQLAlchemy модель
from app.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/users", tags=["users"])

# 🔹 Получить всех пользователей
@router.get("/", response_model=List[User])
def get_users(db: Session = get_db()):
	users = db.query(UserORM).all()
	return users

# 🔹 Получить пользователя по ID
@router.get("/{user_id}", response_model=User)
def get_user(user_id: int, db: Session = get_db()):
	user = db.query(UserORM).filter(UserORM.id == user_id).first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	return user

# 🔹 Добавить нового пользователя
@router.post("/", response_model=User)
def create_user(user: User, db: Session = get_db()):
	new_user = UserORM(**user.dict())
	db.add(new_user)
	db.commit()
	db.refresh(new_user)
	return new_user

# 🔹 Удалить пользователя
@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = get_db()):
	user = db.query(UserORM).filter(UserORM.id == user_id).first()
	if not user:
		raise HTTPException(status_code=404, detail="User not found")
	db.delete(user)
	db.commit()
	return {"detail": "User deleted"}
