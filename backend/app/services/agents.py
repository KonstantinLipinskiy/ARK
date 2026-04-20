from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate

class AgentsService:
	def __init__(self):
		# Инициализация LLM (можно заменить на локальную модель)
		self.llm = OpenAI(temperature=0)

		# Определяем инструменты, которые агент может использовать
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
			)
		]

		# Инициализация агента
		self.agent = initialize_agent(
			tools=self.tools,
			llm=self.llm,
			agent="zero-shot-react-description",
			verbose=True
		)

	def analyze_signal(self, signal: dict) -> str:
		"""Пример функции анализа сигнала."""
		return f"Signal {signal} analyzed."

	def generate_report(self, trades: list[dict]) -> str:
		"""Пример генерации отчёта."""
		return f"Generated report for {len(trades)} trades."

	def run_agent(self, query: str) -> str:
		"""Запуск агента с произвольным запросом."""
		return self.agent.run(query)