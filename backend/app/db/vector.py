from qdrant_client import QdrantClient
from qdrant_client.http import models

class VectorDB:
	def __init__(self, host: str = "localhost", port: int = 6333, collection_name: str = "arkbot_vectors"):
		self.client = QdrantClient(host=host, port=port)
		self.collection_name = collection_name
		self._init_collection()

	def _init_collection(self):
		"""Создаёт коллекцию, если она не существует."""
		self.client.recreate_collection(
			collection_name=self.collection_name,
			vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
		)

	def insert_vector(self, vector: list[float], payload: dict):
		"""Добавляет эмбеддинг в Qdrant."""
		self.client.upsert(
			collection_name=self.collection_name,
			points=[
					models.PointStruct(
						id=payload.get("id"),
						vector=vector,
						payload=payload
					)
			]
		)

	def search(self, query_vector: list[float], top_k: int = 5):
		"""Поиск ближайших эмбеддингов."""
		results = self.client.search(
			collection_name=self.collection_name,
			query_vector=query_vector,
			limit=top_k
		)
		return results

	def delete(self, point_id: int):
		"""Удаляет точку по ID."""
		self.client.delete(
			collection_name=self.collection_name,
			points_selector=models.PointIdsSelector(point_ids=[point_id])
		)