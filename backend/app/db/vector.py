# app/db/vector.py
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.utils.logger import logger

class VectorDB:
	def __init__(
		self,
		host: str = os.getenv("QDRANT_HOST", "localhost"),
		port: int = int(os.getenv("QDRANT_PORT", 6333)),
		collection_name: str = os.getenv("QDRANT_COLLECTION", "arkbot_vectors")
	):
		try:
			self.client = QdrantClient(host=host, port=port)
			self.collection_name = collection_name
			self._init_collection()
		except Exception as e:
			logger.error(f"Ошибка подключения к Qdrant: {e}")
			raise

	def _init_collection(self):
		"""Создаёт коллекцию, если она не существует."""
		try:
			self.client.recreate_collection(
					collection_name=self.collection_name,
					vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
			)
			logger.info(f"Коллекция {self.collection_name} инициализирована")
		except Exception as e:
			logger.error(f"Ошибка инициализации коллекции: {e}")

	def insert_vector(self, vector: list[float], payload: dict):
		"""Добавляет один эмбеддинг в Qdrant."""
		try:
			self.client.upsert(
					collection_name=self.collection_name,
					points=[models.PointStruct(id=payload.get("id"), vector=vector, payload=payload)]
			)
			logger.info(f"Эмбеддинг вставлен: {payload}")
		except Exception as e:
			logger.error(f"Ошибка вставки эмбеддинга: {e}")

	def batch_insert(self, vectors: list[list[float]], payloads: list[dict]):
		"""Массовая вставка эмбеддингов."""
		try:
			points = [
					models.PointStruct(id=p.get("id"), vector=v, payload=p)
					for v, p in zip(vectors, payloads)
			]
			self.client.upsert(collection_name=self.collection_name, points=points)
			logger.info(f"Batch insert: {len(points)} эмбеддингов")
		except Exception as e:
			logger.error(f"Ошибка batch insert: {e}")

	def update_vector(self, point_id: int, vector: list[float] = None, payload: dict = None):
		"""Обновляет существующий эмбеддинг или payload."""
		try:
			self.client.upsert(
					collection_name=self.collection_name,
					points=[models.PointStruct(id=point_id, vector=vector, payload=payload)]
			)
			logger.info(f"Эмбеддинг обновлён: id={point_id}")
		except Exception as e:
			logger.error(f"Ошибка обновления эмбеддинга: {e}")

	def search(self, query_vector: list[float], top_k: int = 5):
		"""Поиск ближайших эмбеддингов."""
		try:
			results = self.client.search(
					collection_name=self.collection_name,
					query_vector=query_vector,
					limit=top_k
			)
			return results
		except Exception as e:
			logger.error(f"Ошибка поиска: {e}")
			return []

	def search_with_filter(self, query_vector: list[float], filters: dict, top_k: int = 5):
		"""Поиск с фильтрацией по payload."""
		try:
			qdrant_filter = models.Filter(
					must=[models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in filters.items()]
			)
			results = self.client.search(
					collection_name=self.collection_name,
					query_vector=query_vector,
					limit=top_k,
					query_filter=qdrant_filter
			)
			return results
		except Exception as e:
			logger.error(f"Ошибка поиска с фильтром: {e}")
			return []

	def count_points(self) -> int:
		"""Подсчёт количества точек в коллекции."""
		try:
			info = self.client.get_collection(self.collection_name)
			return info.points_count
		except Exception as e:
			logger.error(f"Ошибка получения статистики: {e}")
			return 0

	def delete(self, point_id: int):
		"""Удаляет точку по ID."""
		try:
			self.client.delete(
					collection_name=self.collection_name,
					points_selector=models.PointIdsSelector(point_ids=[point_id])
			)
			logger.info(f"Эмбеддинг удалён: id={point_id}")
		except Exception as e:
			logger.error(f"Ошибка удаления эмбеддинга: {e}")
