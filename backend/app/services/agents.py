# app/services/agents.py
from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI
from app.services.reports import ReportsService
from app.db.vector import VectorDB
from app.utils.metrics import calculate_metrics
from app.config import RISK_CONFIG
from app.services.orders import OrdersService
from app.utils.logger import logger

class AgentsService:
	def __init__(self, llm_provider: str = "openai", temperature: float = 0):
		# Инициализация LLM (можно переключать провайдер)
		if llm_provider == "openai":
			self.llm = OpenAI(temperature=temperature)
		# TODO: добавить HuggingFace, LLaMA, Mistral

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

	def search_vector(self, query: str) -> str:
		results = self.vector.search(query)
		return f"Vector search results: {results}"

	def run_agent(self, query: str) -> str:
		logger.info(f"Запуск агента с запросом: {query}")
		return self.agent.run(query)
