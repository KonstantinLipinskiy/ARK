from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from app.utils.security import decode_jwt_token

class JWTMiddleware(BaseHTTPMiddleware):
	"""
	Middleware для проверки JWT токена.
	Добавляет user_id и role в request.state, если токен валиден.
	"""

	def __init__(self, app):
		super().__init__(app)
		self.security = HTTPBearer()

	async def dispatch(self, request: Request, call_next):
		# Проверяем только защищённые маршруты (например, /signals, /trades, /users)
		if request.url.path.startswith(("/signals", "/trades", "/users")):
			try:
					credentials: HTTPAuthorizationCredentials = await self.security(request)
					token = credentials.credentials
					payload = decode_jwt_token(token)
					if not payload:
						raise HTTPException(status_code=401, detail="Invalid or expired token")

					# Добавляем user_id и role в request.state
					request.state.user_id = payload.get("user_id")
					request.state.role = payload.get("role")

			except HTTPException as e:
					raise e
			except Exception:
					raise HTTPException(status_code=401, detail="Authorization failed")

		response = await call_next(request)
		return response
