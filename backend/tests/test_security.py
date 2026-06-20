# tests/test_security.py
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.security import HTTPBearer
from app.utils import security
from app.utils.logger import logger

app = FastAPI()

# Тестовые эндпоинты для проверки Depends
@app.get("/user")
async def user_endpoint(current_user: dict = Depends(security.get_current_user)):
	return current_user

@app.get("/admin")
async def admin_endpoint(current_admin: dict = Depends(security.get_current_admin)):
	return current_admin


# ---------- Пароли ----------
def test_password_hash_and_verify():
	password = "securepassword123"
	hashed = security.hash_password(password)
	assert security.verify_password(password, hashed)
	assert not security.verify_password("wrongpassword", hashed)


# ---------- JWT ----------
def test_create_and_decode_jwt():
	data = {"user_id": 1, "role": "trader"}
	token = security.create_access_token(data, expires_minutes=1)
	payload = security.decode_jwt_token(token)
	assert payload is not None
	assert payload["user_id"] == 1
	assert payload["role"] == "trader"


def test_decode_invalid_jwt(caplog):
	caplog.set_level("ERROR", logger=logger.name)
	invalid_token = "invalid.token.value"
	payload = security.decode_jwt_token(invalid_token)
	assert payload is None
	assert any("❌ Невалидный JWT токен" in message for message in caplog.messages)


# ---------- Depends get_current_user / get_current_admin ----------
client = TestClient(app)

def test_get_current_user_success():
	token = security.create_access_token({"user_id": 42, "role": "trader"}, expires_minutes=1)
	response = client.get("/user", headers={"Authorization": f"Bearer {token}"})
	assert response.status_code == 200
	data = response.json()
	assert data["user_id"] == 42
	assert data["role"] == "trader"


def test_get_current_user_invalid_token():
	response = client.get("/user", headers={"Authorization": "Bearer invalidtoken"})
	assert response.status_code == 401


def test_get_current_admin_success(caplog):
	caplog.set_level("INFO", logger=logger.name)
	token = security.create_access_token({"user_id": 99, "role": "admin"}, expires_minutes=1)
	response = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
	assert response.status_code == 200
	data = response.json()
	assert data["user_id"] == 99
	assert data["role"] == "admin"
	assert any("✅ Admin" in message for message in caplog.messages)


def test_get_current_admin_forbidden():
	token = security.create_access_token({"user_id": 100, "role": "trader"}, expires_minutes=1)
	response = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
	assert response.status_code == 403
