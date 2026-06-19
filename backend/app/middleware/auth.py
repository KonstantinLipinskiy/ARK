# app/middleware/auth.py
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.security import decode_jwt_token
from app.utils.logger import logger

# --- Список защищённых маршрутов вынесен в конфиг ---
PROTECTED_PATHS = ["/signals", "/trades", "/users", "/indicators"]

class JWTMiddleware(BaseHTTPMiddleware):
	"""
	Middleware для проверки JWT токена.
	Добавляет user_id, role и token_type в request.state, если токен валиден.
	"""

	def __init__(self, app):
		super().__init__(app)
		self.security = HTTPBearer()

	async def dispatch(self, request: Request, call_next):
		# Проверяем защищённые маршруты через any()
		if any(request.url.path.startswith(path) for path in PROTECTED_PATHS):
			try:
				credentials: HTTPAuthorizationCredentials = await self.security(request)
				token = credentials.credentials
				payload = decode_jwt_token(token)
				if not payload:
					logger.warning(f"❌ Invalid or expired token for path {request.url.path}")
					raise HTTPException(status_code=401, detail="Invalid or expired token")

				# Проверка типа токена
				token_type = payload.get("token_type")
				if token_type != "access":
					logger.warning(f"❌ Invalid token type '{token_type}' for path {request.url.path}")
					raise HTTPException(status_code=401, detail="Invalid token type")

				# Добавляем user_id и role в request.state
				request.state.user_id = payload.get("user_id")
				request.state.role = payload.get("role")

				# Проверка статуса пользователя
				if payload.get("status") and payload.get("status") != "active":
					logger.error(f"🚫 Blocked user {request.state.user_id} tried to access {request.url.path}")
					raise HTTPException(status_code=403, detail="User is blocked")

			except HTTPException as e:
				# Логируем HTTP ошибки
				logger.error(f"⚠️ Authorization failed: {e.detail} (path: {request.url.path})")
				raise e
			except Exception as e:
				# Логируем неожиданные ошибки
				logger.error(f"❌ Unexpected authorization error: {e} (path: {request.url.path})")
				raise HTTPException(status_code=401, detail="Authorization failed")

		response = await call_next(request)
		return response
