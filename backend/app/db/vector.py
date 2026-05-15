# app/db/vector.py
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.utils.logger import logger
from prometheus_client import Gauge, Counter, Histogram
from app.config import settings   # 🔹 теперь используем централизованный конфиг

# 🔹 Метрики для Prometheus
VECTOR_POINTS_TOTAL = Gauge("vector_points_total", "Total points in Qdrant collection", ["collection"])
VECTOR_SEARCH_TOTAL = Counter("vector_search_total", "Total search queries in Qdrant", ["collection"])
VECTOR_ERRORS_TOTAL = Counter("vector_errors_total", "Total errors in Qdrant operations", ["collection", "operation"])
VECTOR_SEARCH_LATENCY = Histogram("vector_search_latency_seconds", "Search latency in seconds", ["collection"])

class VectorDB:
	def __init__(self):
		try:
			# 🔹 Подключение к Qdrant через параметры из settings
			self.client = QdrantClient(
					host=settings.QDRANT_HOST,
					port=settings.QDRANT_PORT
			)
			self.collection_name = settings.QDRANT_COLLECTION
			self.vector_size = settings.QDRANT_VECTOR_SIZE
			self.distance_metric = getattr(models.Distance, settings.QDRANT_DISTANCE)
			self._init_collection()
		except Exception as e:
			logger.error(f"Ошибка подключения к Qdrant: {e}")
			raise

	def use_collection(self, name: str):
		"""Переключение на другую коллекцию (signals, trades, news, reports, strategies)."""
		self.collection_name = name
		self._init_collection()
		logger.info(f"Переключено на коллекцию: {self.collection_name}")

	def _init_collection(self):
		"""Создаёт коллекцию, если она не существует (без пересоздания)."""
		try:
			collections = [c.name for c in self.client.get_collections().collections]
			if self.collection_name not in collections:
					self.client.create_collection(
						collection_name=self.collection_name,
						vectors_config=models.VectorParams(size=self.vector_size, distance=self.distance_metric)
					)
					logger.info(f"Коллекция {self.collection_name} создана")
			else:
					logger.info(f"Коллекция {self.collection_name} уже существует")
		except Exception as e:
			logger.error(f"Ошибка инициализации коллекции: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="init").inc()

	def insert_vector(self, vector: list[float], payload: dict):
		"""Добавляет один эмбеддинг в Qdrant."""
		try:
			self.client.upsert(
					collection_name=self.collection_name,
					points=[models.PointStruct(id=payload.get("id"), vector=vector, payload=payload)]
			)
			logger.info(f"Эмбеддинг вставлен: {payload}")
			VECTOR_POINTS_TOTAL.labels(collection=self.collection_name).set(self.count_points())
		except Exception as e:
			logger.error(f"Ошибка вставки эмбеддинга: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="insert").inc()
			return {"error": str(e)}

	def batch_insert(self, vectors: list[list[float]], payloads: list[dict]):
		"""Массовая вставка эмбеддингов."""
		try:
			points = [
					models.PointStruct(id=p.get("id"), vector=v, payload=p)
					for v, p in zip(vectors, payloads)
			]
			self.client.upsert(collection_name=self.collection_name, points=points)
			logger.info(f"Batch insert: {len(points)} эмбеддингов")
			VECTOR_POINTS_TOTAL.labels(collection=self.collection_name).set(self.count_points())
		except Exception as e:
			logger.error(f"Ошибка batch insert: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="batch_insert").inc()
			return {"error": str(e)}

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
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="update").inc()
			return {"error": str(e)}

	def search(self, query_vector: list[float], top_k: int = 5):
		"""Поиск ближайших эмбеддингов."""
		try:
			with VECTOR_SEARCH_LATENCY.labels(collection=self.collection_name).time():
					results = self.client.search(
						collection_name=self.collection_name,
						query_vector=query_vector,
						limit=top_k
					)
			VECTOR_SEARCH_TOTAL.labels(collection=self.collection_name).inc()
			return results
		except Exception as e:
			logger.error(f"Ошибка поиска: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="search").inc()
			return {"error": str(e)}

	def search_with_filter(self, query_vector: list[float], filters: dict, top_k: int = 5):
		"""Поиск с фильтрацией по payload."""
		try:
			qdrant_filter = models.Filter(
					must=[models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in filters.items()]
			)
			with VECTOR_SEARCH_LATENCY.labels(collection=self.collection_name).time():
					results = self.client.search(
						collection_name=self.collection_name,
						query_vector=query_vector,
						limit=top_k,
						query_filter=qdrant_filter
					)
			VECTOR_SEARCH_TOTAL.labels(collection=self.collection_name).inc()
			return results
		except Exception as e:
			logger.error(f"Ошибка поиска с фильтром: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="search_with_filter").inc()
			return {"error": str(e)}

	def count_points(self) -> int:
		"""Подсчёт количества точек в коллекции."""
		try:
			info = self.client.get_collection(self.collection_name)
			return info.points_count
		except Exception as e:
			logger.error(f"Ошибка получения статистики: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="count").inc()
			return 0

	def delete(self, point_id: int):
		"""Удаляет точку по ID."""
		try:
			self.client.delete(
					collection_name=self.collection_name,
					points_selector=models.PointIdsSelector(point_ids=[point_id])
			)
			logger.info(f"Эмбеддинг удалён: id={point_id}")
			VECTOR_POINTS_TOTAL.labels(collection=self.collection_name).set(self.count_points())
		except Exception as e:
			logger.error(f"Ошибка удаления эмбеддинга: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="delete").inc()
			return {"error": str(e)}

	def drop_collection(self):
		"""Удаляет всю коллекцию (для тестов или пересоздания)."""
		try:
			self.client.delete_collection(self.collection_name)
			logger.info(f"Коллекция {self.collection_name} удалена")
		except Exception as e:
			logger.error(f"Ошибка удаления коллекции: {e}")
			VECTOR_ERRORS_TOTAL.labels(collection=self.collection_name, operation="drop_collection").inc()
			return {"error": str(e)}
