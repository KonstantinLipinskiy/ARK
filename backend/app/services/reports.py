from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from app.db.vector import VectorDB

class ReportsService:
	def __init__(self):
		# Инициализация LLM
		self.llm = OpenAI(temperature=0)
		# Подключение к Qdrant
		self.vector_db = VectorDB()
		# Настройка RAG цепочки
		self.qa_chain = RetrievalQA.from_chain_type(
			llm=self.llm,
			retriever=self.vector_db.client.as_retriever(),
			chain_type="stuff"
		)

	def generate_report(self, query: str) -> str:
		"""Генерация отчёта на основе запроса и данных из Qdrant."""
		return self.qa_chain.run(query)

	def add_document(self, vector: list[float], payload: dict):
		"""Добавление документа в базу знаний."""
		self.vector_db.insert_vector(vector, payload)

	def search_documents(self, query_vector: list[float], top_k: int = 5):
		"""Поиск релевантных документов."""
		return self.vector_db.search(query_vector, top_k)