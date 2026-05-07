from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.session import get_db
from app.db.schemas import UserORM
from app.models.user import UserCreate, UserLogin, UserOut
from app.utils.security import hash_password, verify_password, create_jwt_token

router = APIRouter(prefix="/auth", tags=["auth"])

# 🔹 Регистрация нового пользователя
@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
	# Проверяем, что email уникален
	result = await db.execute(select(UserORM).where(UserORM.email == user.email))
	existing_user = result.scalar_one_or_none()
	if existing_user:
		raise HTTPException(status_code=400, detail="User with this email already exists")

	# Хэшируем пароль
	salt, password_hash = hash_password(user.password)

	new_user = UserORM(
		username=user.username,
		email=user.email,
		role=user.role,
		status="active",
		password_hash=password_hash,
		salt=salt,
		telegram_id=user.telegram_id,
		settings=user.settings
	)
	db.add(new_user)
	await db.commit()
	await db.refresh(new_user)
	return new_user

# 🔹 Логин пользователя
@router.post("/login")
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(UserORM).where(UserORM.email == credentials.email))
	user = result.scalar_one_or_none()
	if not user or not verify_password(credentials.password, user.salt, user.password_hash):
		raise HTTPException(status_code=401, detail="Invalid credentials")

	# Генерация JWT токена
	token = create_jwt_token({"user_id": user.id, "role": user.role})
	return {"access_token": token, "token_type": "bearer"}
