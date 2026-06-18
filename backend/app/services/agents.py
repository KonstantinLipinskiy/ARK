# app/services/agents.py
from langchain.agents import initialize_agent, Tool
from langchain_openai import OpenAI
from langchain_huggingface import HuggingFaceHub
from langchain_community.llms import LlamaCpp
from langchain_community.memory import ConversationBufferMemory

from app.services.reports import ReportsService
from app.db.vector import VectorDB
from app.utils.metrics import calculate_metrics, ml_accuracy, ml_loss, ml_precision, ml_recall
from app.config import settings
from app.services.orders import OrdersService
from app.utils.logger import logger


class AgentsService:
	def __init__(self):
		"""
		Инициализация LLM с гибкостью выбора провайдера.
		Все параметры берутся из config.py (.env).
		"""
		self.llm = None
		provider = settings.LLM_PROVIDER.lower()
		model_name = settings.LLM_MODEL_NAME
		model_path = settings.LLM_MODEL_PATH
		temperature = settings.LLM_TEMPERATURE
		top_p = settings.LLM_TOP_P
		max_tokens = settings.LLM_MAX_TOKENS

		try:
			if provider == "openai":
				self.llm = OpenAI(
					temperature=temperature,
					max_tokens=max_tokens,
					top_p=top_p
				)
			elif provider == "huggingface":
				self.llm = HuggingFaceHub(
					repo_id=model_name,
					model_kwargs={
						"temperature": temperature,
						"top_p": top_p,
						"max_length": max_tokens
					}
				)
			elif provider == "llama":
				self.llm = LlamaCpp(
					model_path=model_path,
					temperature=temperature,
					top_p=top_p,
					max_tokens=max_tokens
				)
			elif provider == "mistral":
				self.llm = HuggingFaceHub(
					repo_id=model_name,
					model_kwargs={
						"temperature": temperature,
						"top_p": top_p,
						"max_length": max_tokens
					}
				)
			else:
				raise ValueError(f"Неизвестный провайдер LLM: {provider}")
		except Exception as e:
			logger.error(f"Ошибка инициализации LLM ({provider}): {e}")
			raise

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
				description="Подсчёт winrate, профита и ML-метрик"
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

		# Подключаем память агента
		memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

		# Инициализация агента
		self.agent = initialize_agent(
			tools=self.tools,
			llm=self.llm,
			agent="zero-shot-react-description",
			verbose=True,
			memory=memory
		)

	# --- Инструменты ---
	def analyze_signal(self, signal: dict) -> str:
		action = signal.get("action", "").lower()
		strength = signal.get("strength", 0)
		test_flag = signal.get("test", False)

		if action not in ["buy", "sell"]:
			logger.info(f"Сигнал проигнорирован: неключевой action={action}")
			return "⚠️ Сигнал проигнорирован (неключевой)"
		if strength < settings.MIN_SIGNAL_STRENGTH:
			logger.info(f"Сигнал проигнорирован: слабая сила={strength}")
			return "⚠️ Сигнал проигнорирован (слабый)"
		if test_flag and not settings.ALLOW_TEST_SIGNALS:
			logger.info("Сигнал проигнорирован: тестовый")
			return "⚠️ Сигнал проигнорирован (тестовый)"

		logger.info(f"Сигнал принят: {signal}")
		return f"✅ Ключевой сигнал принят: {signal}"

	def generate_report(self, trades: list[dict], output_format: str = "text") -> str:
		"""
		Генерация RAG-отчёта по сделкам с поддержкой разных форматов.
		Форматы: text | json | markdown | html
		"""
		try:
			report = self.reports.generate_rag_report(trades, output_format=output_format)
			logger.info(f"RAG отчёт успешно сформирован агентом, формат={output_format}")
			return report
		except Exception as e:
			logger.error(f"Ошибка генерации отчёта агентом: {e}")
			return f"❌ Ошибка генерации отчёта: {e}"

	def check_risk(self, trade: dict) -> str:
		max_loss = settings.MAX_LOSS_PER_TRADE
		if trade.get("loss", 0) > max_loss:
			return f"❌ Риск превышен: убыток {trade['loss']} > {max_loss}"
		return "✅ Риск в пределах лимита"

	def execute_order(self, order: dict) -> str:
		result = self.orders.place_order(order)
		return f"Order executed: {result}"

	def metrics_report(self, trades: list[dict]) -> str:
		metrics = calculate_metrics(trades)
		return (
			f"Winrate: {metrics['winrate']:.2%}, Profit: {metrics['total_profit']:.2f}, "
			f"ML Accuracy: {ml_accuracy._value.get():.2f}, "
			f"Precision: {ml_precision._value.get():.2f}, "
			f"Recall: {ml_recall._value.get():.2f}, "
			f"Loss: {ml_loss._value.get():.4f}"
		)

	def search_vector(self, query: dict) -> str:
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
