# app/services/agents.py
from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI, HuggingFaceHub
from app.services.reports import ReportsService
from app.db.vector import VectorDB
from app.utils.metrics import calculate_metrics
from app.config import RISK_CONFIG
from app.services.orders import OrdersService
from app.utils.logger import logger

# 🔹 Дополнительно можно подключить локальные модели (пример)
try:
	from langchain.llms import LlamaCpp
except ImportError:
	LlamaCpp = None

class AgentsService:
	def __init__(
		self,
		llm_provider: str = "openai",
		temperature: float = 0.0,
		top_p: float = 1.0,
		max_tokens: int = 512,
		model_name: str | None = None
	):
		"""
		Инициализация LLM с гибкостью выбора провайдера.
		llm_provider: "openai", "huggingface", "llama", "mistral"
		"""
		self.llm = None

		if llm_provider == "openai":
			self.llm = OpenAI(
					temperature=temperature,
					max_tokens=max_tokens,
					top_p=top_p
			)
		elif llm_provider == "huggingface":
			# Требует настройки HUGGINGFACEHUB_API_TOKEN
			self.llm = HuggingFaceHub(
					repo_id=model_name or "google/flan-t5-large",
					model_kwargs={
						"temperature": temperature,
						"top_p": top_p,
						"max_length": max_tokens
					}
			)
		elif llm_provider == "llama" and LlamaCpp:
			self.llm = LlamaCpp(
					model_path=model_name or "./models/llama-7b.ggmlv3.q4_0.bin",
					temperature=temperature,
					top_p=top_p,
					max_tokens=max_tokens
			)
		elif llm_provider == "mistral":
			# Заглушка: интеграция через HuggingFace
			self.llm = HuggingFaceHub(
					repo_id=model_name or "mistralai/Mistral-7B-v0.1",
					model_kwargs={
						"temperature": temperature,
						"top_p": top_p,
						"max_length": max_tokens
					}
			)
		else:
			raise ValueError(f"Неизвестный провайдер LLM: {llm_provider}")

		# Инициализация вспомогательных сервисов
		self.vector = VectorDB()
		self.reports = ReportsService()
		self.orders = OrdersService()

		# Определяем инструменты
		self.tools = [
			Tool(
					name="Signal Analyzer",
					func=self.analyze_signal,
					description="Анализ торгового сигнала и выдача прогноза"
			),
			Tool(
					name="Report Generator",
					func=self.generate_report,
					description="Создание отчёта по сделкам"
			),
			Tool(
					name="Risk Manager",
					func=self.check_risk,
					description="Проверка лимитов риск-менеджмента"
			),
			Tool(
					name="Order Executor",
					func=self.execute_order,
					description="Выставление торгового ордера"
			),
			Tool(
					name="Metrics Reporter",
					func=self.metrics_report,
					description="Подсчёт winrate, профита и метрик"
			),
			Tool(
					name="Vector Search",
					func=self.search_vector,
					description="Поиск по эмбеддингам сигналов и сделок"
			),
			Tool(
					name="Vector Search with Filter",
					func=self.search_vector_with_filter,
					description="Поиск по эмбеддингам с фильтрацией по payload (например, стратегия, пользователь)"
			)
		]

		# Инициализация агента
		self.agent = initialize_agent(
			tools=self.tools,
			llm=self.llm,
			agent="zero-shot-react-description",
			verbose=True
		)

	# --- Инструменты ---
	def analyze_signal(self, signal: dict) -> str:
		return f"Signal {signal} analyzed."

	def generate_report(self, trades: list[dict]) -> str:
		return self.reports.generate_rag_report(trades)

	def check_risk(self, trade: dict) -> str:
		max_loss = RISK_CONFIG.get("max_loss_per_trade", 0)
		if trade.get("loss", 0) > max_loss:
			return f"❌ Риск превышен: убыток {trade['loss']} > {max_loss}"
		return "✅ Риск в пределах лимита"

	def execute_order(self, order: dict) -> str:
		result = self.orders.place_order(order)
		return f"Order executed: {result}"

	def metrics_report(self, trades: list[dict]) -> str:
		metrics = calculate_metrics(trades)
		return f"Winrate: {metrics['winrate']:.2%}, Profit: {metrics['total_profit']:.2f}"

	def search_vector(self, query: dict) -> str:
		"""
		Поиск по эмбеддингам.
		query = {"vector": [...], "collection": "signals", "top_k": 5}
		"""
		try:
			collection = query.get("collection", "signals")
			self.vector.use_collection(collection)
			vector = query.get("vector")
			top_k = query.get("top_k", 5)
			results = self.vector.search(vector, top_k)
			return f"Vector search in {collection}: {results}"
		except Exception as e:
			logger.error(f"Ошибка поиска векторной базы: {e}", extra={"operation": "search", "collection": query.get("collection")})
			return "Ошибка поиска"

	def search_vector_with_filter(self, query: dict) -> str:
		"""
		Поиск по эмбеддингам с фильтрацией.
		query = {
			"vector": [...],
			"collection": "signals",
			"filters": {"strategy": "scalping", "user_id": 123},
			"top_k": 5
		}
		"""
		try:
			collection = query.get("collection", "signals")
			self.vector.use_collection(collection)
			vector = query.get("vector")
			filters = query.get("filters", {})
			top_k = query.get("top_k", 5)
			results = self.vector.search_with_filter(vector, filters, top_k)
			return f"Filtered vector search in {collection} with {filters}: {results}"
		except Exception as e:
			logger.error(f"Ошибка поиска с фильтром: {e}", extra={"operation": "search_with_filter", "collection": query.get("collection")})
			return "Ошибка поиска с фильтром"

	def run_agent(self, query: str) -> str:
		logger.info(f"Запуск агента с запросом: {query}")
		return self.agent.run(query)
