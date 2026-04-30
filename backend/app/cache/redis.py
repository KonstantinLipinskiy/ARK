import json
import logging
from redis.asyncio import Redis
from app.utils.logger import logger
from app.config import REDIS_CONFIG


class RedisCache:
	def __init__(self,
					host: str = REDIS_CONFIG["host"],
					port: int = REDIS_CONFIG["port"],
					db: int = REDIS_CONFIG["db"]):
		self.client = Redis(host=host, port=port, db=db, decode_responses=True)


	async def set(self, key: str, value: dict, expire: int = 60):
		"""Сохраняет данные в Redis с TTL."""
		try:
			await self.client.set(key, json.dumps(value), ex=expire)
		except Exception as e:
			logger.error(f"❌ Redis set error: {e}")

	async def get(self, key: str) -> dict | None:
		"""Получает данные из Redis."""
		try:
			data = await self.client.get(key)
			return json.loads(data) if data else None
		except Exception as e:
			logger.error(f"❌ Redis get error: {e}")
			return None

	async def delete(self, key: str):
		"""Удаляет ключ из Redis."""
		try:
			await self.client.delete(key)
		except Exception as e:
			logger.error(f"❌ Redis delete error: {e}")

	async def publish(self, channel: str, message: dict):
		"""Публикует сообщение в канал Redis (pub/sub)."""
		try:
			await self.client.publish(channel, json.dumps(message))
		except Exception as e:
			logger.error(f"❌ Redis publish error: {e}")

	async def subscribe(self, channel: str):
		"""Подписка на канал Redis."""
		try:
			pubsub = self.client.pubsub()
			await pubsub.subscribe(channel)
			return pubsub
		except Exception as e:
			logger.error(f"❌ Redis subscribe error: {e}")
			return None

	async def exists(self, key: str) -> bool:
		"""Проверка наличия ключа."""
		return await self.client.exists(key) > 0

	async def flush(self):
		"""Очистка базы (например, при тестах)."""
		await self.client.flushdb()
