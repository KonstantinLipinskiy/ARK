import redis
import json

class RedisCache:
	def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
		self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

	def set(self, key: str, value: dict, expire: int = 60):
		"""Сохраняет данные в Redis с TTL."""
		self.client.set(key, json.dumps(value), ex=expire)

	def get(self, key: str) -> dict | None:
		"""Получает данные из Redis."""
		data = self.client.get(key)
		return json.loads(data) if data else None

	def delete(self, key: str):
		"""Удаляет ключ из Redis."""
		self.client.delete(key)

	def publish(self, channel: str, message: dict):
		"""Публикует сообщение в канал Redis (pub/sub)."""
		self.client.publish(channel, json.dumps(message))

	def subscribe(self, channel: str):
		"""Подписка на канал Redis."""
		pubsub = self.client.pubsub()
		pubsub.subscribe(channel)
		return pubsub