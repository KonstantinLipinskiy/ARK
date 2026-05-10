# app/cache/redis.py
import json
from redis.asyncio import Redis
from app.utils.logger import logger
from app.config import REDIS_CONFIG


class RedisCache:
	def __init__(self,
					host: str = REDIS_CONFIG["host"],
					port: int = REDIS_CONFIG["port"],
					db: int = REDIS_CONFIG["db"]):
		self.host = host
		self.port = port
		self.db = db
		self.client = Redis(host=host, port=port, db=db, decode_responses=True)

	async def set(self, key: str, value: dict, expire: int = 60):
		"""Сохраняет данные в Redis с TTL."""
		try:
			await self.client.set(key, json.dumps(value), ex=expire)
			logger.debug(f"✅ Redis set: {key} → {value}")
		except Exception as e:
			logger.error(f"❌ Redis set error: {e}")

	async def get(self, key: str) -> dict | None:
		"""Получает данные из Redis."""
		try:
			data = await self.client.get(key)
			if data:
					logger.debug(f"✅ Redis get: {key}")
					return json.loads(data)
			return None
		except Exception as e:
			logger.error(f"❌ Redis get error: {e}")
			return None

	async def set_json(self, key: str, value: dict, expire: int = 60):
		"""Удобный метод для сохранения JSON."""
		return await self.set(key, value, expire)

	async def get_json(self, key: str) -> dict | None:
		"""Удобный метод для получения JSON."""
		return await self.get(key)

	async def delete(self, key: str):
		"""Удаляет ключ из Redis."""
		try:
			await self.client.delete(key)
			logger.debug(f"🗑️ Redis delete: {key}")
		except Exception as e:
			logger.error(f"❌ Redis delete error: {e}")

	async def publish(self, channel: str, message: dict):
		"""Публикует сообщение в канал Redis (pub/sub)."""
		try:
			await self.client.publish(channel, json.dumps(message))
			logger.debug(f"📤 Redis publish to {channel}: {message}")
		except Exception as e:
			logger.error(f"❌ Redis publish error: {e}")

	async def subscribe(self, channel: str):
		"""Подписка на канал Redis."""
		try:
			pubsub = self.client.pubsub()
			await pubsub.subscribe(channel)
			logger.info(f"📥 Redis subscribed to channel: {channel}")
			return pubsub
		except Exception as e:
			logger.error(f"❌ Redis subscribe error: {e}")
			return None

	async def exists(self, key: str) -> bool:
		"""Проверка наличия ключа."""
		try:
			result = await self.client.exists(key)
			logger.debug(f"🔎 Redis exists: {key} → {result > 0}")
			return result > 0
		except Exception as e:
			logger.error(f"❌ Redis exists error: {e}")
			return False

	async def flush(self):
		"""Очистка базы (например, при тестах)."""
		try:
			await self.client.flushdb()
			logger.warning("⚠️ Redis flush: database cleared")
		except Exception as e:
			logger.error(f"❌ Redis flush error: {e}")

	async def keys(self, pattern: str = "*") -> list[str]:
		"""Получение списка ключей по шаблону."""
		try:
			result = await self.client.keys(pattern)
			logger.debug(f"🔑 Redis keys: {result}")
			return result
		except Exception as e:
			logger.error(f"❌ Redis keys error: {e}")
			return []

	async def health_check(self) -> bool:
		"""Проверка доступности Redis."""
		try:
			pong = await self.client.ping()
			logger.debug("✅ Redis health check: PONG")
			return pong
		except Exception as e:
			logger.error(f"❌ Redis health check failed: {e}")
			return False

	async def switch_db(self, db: int):
		"""Переключение на другую базу Redis."""
		try:
			self.db = db
			self.client = Redis(host=self.host, port=self.port, db=db, decode_responses=True)
			logger.info(f"🔄 Redis switched to DB {db}")
		except Exception as e:
			logger.error(f"❌ Redis switch_db error: {e}")
