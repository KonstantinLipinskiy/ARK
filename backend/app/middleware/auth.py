from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.security import decode_jwt_token

class JWTMiddleware(BaseHTTPMiddleware):
	"""
	Middleware для проверки JWT токена.
	Добавляет user_id, role и token_type в request.state, если токен валиден.
	"""

	def __init__(self, app):
		super().__init__(app)
		self.security = HTTPBearer()

	async def dispatch(self, request: Request, call_next):
		# Проверяем защищённые маршруты (теперь включая /indicators)
		if request.url.path.startswith(("/signals", "/trades", "/users", "/indicators")):
			try:
					credentials: HTTPAuthorizationCredentials = await self.security(request)
					token = credentials.credentials
					payload = decode_jwt_token(token)
					if not payload:
						raise HTTPException(status_code=401, detail="Invalid or expired token")

					# Проверка типа токена
					token_type = payload.get("token_type")
					if token_type != "access":
						raise HTTPException(status_code=401, detail="Invalid token type")

					# Добавляем user_id и role в request.state
					request.state.user_id = payload.get("user_id")
					request.state.role = payload.get("role")

					# Дополнительно можно проверять статус пользователя, если он включён в payload
					if payload.get("status") and payload.get("status") != "active":
						raise HTTPException(status_code=403, detail="User is blocked")

			except HTTPException as e:
					raise e
			except Exception:
					raise HTTPException(status_code=401, detail="Authorization failed")

		response = await call_next(request)
		return response
