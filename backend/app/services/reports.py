# app/services/reports.py
import time
from typing import List, Dict, Optional
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI
from app.db.vector import VectorDB
from app.utils.metrics import calculate_metrics
from app.services.ml import MLService
from app.utils.logger import logger
from prometheus_client import Counter, Gauge
import pandas as pd
from fpdf import FPDF
from jinja2 import Template

# 🔹 Метрики Prometheus
REPORT_REQUESTS_TOTAL = Counter("report_requests_total", "Total RAG report requests")
REPORT_AVG_RESPONSE_TIME = Gauge("report_avg_response_time", "Average response time for RAG reports")

class ReportsService:
	def __init__(self, collection_name: str = "trades"):
		# Инициализация LLM
		self.llm = OpenAI(temperature=0)
		# Подключение к Qdrant
		self.vector_db = VectorDB(collection_name=collection_name)
		# Настройка RAG цепочки
		self.qa_chain = RetrievalQA.from_chain_type(
			llm=self.llm,
			retriever=self.vector_db.client.as_retriever(),
			chain_type="stuff"
		)
		# ML сервис
		self.ml = MLService()
		# Метрики
		self.requests_count = 0
		self.total_time = 0.0

	def use_collection(self, name: str):
		"""Переключение коллекции для отчётов."""
		self.vector_db.use_collection(name)

	def generate_report(self, query: str) -> str:
		"""Генерация текстового отчёта на основе запроса и данных из Qdrant."""
		self.requests_count += 1
		REPORT_REQUESTS_TOTAL.inc()
		start = time.time()
		result = self.qa_chain.run(query)
		duration = time.time() - start
		self.total_time += duration
		REPORT_AVG_RESPONSE_TIME.set(self.total_time / self.requests_count)
		return result

	def generate_rag_report(
		self,
		trades: List[Dict],
		filters: Optional[Dict] = None,
		limit: int = 100
	) -> str:
		"""Комплексный RAG-отчёт с метриками, ML прогнозами и сравнением стратегий/пользователей."""
		self.requests_count += 1
		REPORT_REQUESTS_TOTAL.inc()
		start = time.time()

		# Метрики
		metrics = calculate_metrics(trades)

		# ML прогноз
		ml_summary = ""
		try:
			if trades:
					features = {
						"ema": trades[-1].get("ema", 0.0),
						"rsi": trades[-1].get("rsi", 0.0),
						"macd": trades[-1].get("macd", 0.0),
						"hour": trades[-1].get("hour", 0),
						"atr": trades[-1].get("atr", 0.0)
					}
					prob = self.ml.predict_signal(features)
					ml_summary = f"ML прогноз по последнему сигналу: {prob:.2f}"
		except Exception as e:
			logger.error(f"Ошибка ML прогноза: {e}")

		# 🔹 Поиск документов в Qdrant с фильтрацией
		search_results = []
		try:
			query_vector = [0.0] * 768
			if filters:
					search_results = self.vector_db.search_with_filter(query_vector, filters, limit)
			else:
					search_results = self.vector_db.search(query_vector, limit)
		except Exception as e:
			logger.error(f"Ошибка поиска документов для отчёта: {e}")

		# 🔹 Сравнение стратегий и пользователей
		comparison_summary = ""
		try:
			df = pd.DataFrame(trades)
			if not df.empty and "user_id" in df.columns and "strategy" in df.columns:
					grouped = df.groupby(["user_id", "strategy"]).apply(lambda g: calculate_metrics(g.to_dict("records")))
					comparison_summary = "\nСравнение стратегий и пользователей:\n"
					for (user, strat), m in grouped.items():
						comparison_summary += f"👤 User {user}, Strategy {strat}: Winrate={m['winrate']:.2%}, Profit={m['total_profit']:.2f}\n"
		except Exception as e:
			logger.error(f"Ошибка сравнения стратегий/пользователей: {e}")

		report = (
			f"📊 RAG Отчёт\n"
			f"Всего сделок: {metrics['trades_count']}\n"
			f"Winrate: {metrics['winrate']:.2%}\n"
			f"Profit: {metrics['total_profit']:.2f}\n"
			f"Drawdown: {metrics['max_drawdown']:.2f}\n"
			f"Sharpe: {metrics['sharpe_ratio']:.2f}\n"
			f"Sortino: {metrics['sortino_ratio']:.2f}\n"
			f"Profit Factor: {metrics['profit_factor']:.2f}\n"
			f"Макс. серия побед: {metrics['max_consecutive_wins']}\n"
			f"Макс. серия поражений: {metrics['max_consecutive_losses']}\n"
			f"{ml_summary}\n"
			f"🔎 Найдено документов: {len(search_results)}\n"
			f"{comparison_summary}"
		)

		duration = time.time() - start
		self.total_time += duration
		REPORT_AVG_RESPONSE_TIME.set(self.total_time / self.requests_count)
		return report

	def export_report_pdf(self, report_text: str, filename: str = "report.pdf"):
		"""Экспорт отчёта в PDF."""
		try:
			pdf = FPDF()
			pdf.add_page()
			pdf.set_font("Arial", size=12)
			for line in report_text.split("\n"):
					pdf.multi_cell(0, 10, line)
			pdf.output(filename)
			logger.info(f"PDF отчёт сохранён: {filename}")
		except Exception as e:
			logger.error(f"Ошибка экспорта PDF: {e}")

	def export_report_html(self, report_text: str, filename: str = "report.html"):
		"""Экспорт отчёта в HTML."""
		try:
			template = Template("""
			<html>
			<head><title>RAG Report</title></head>
			<body>
			<pre>{{ report }}</pre>
			</body>
			</html>
			""")
			html_content = template.render(report=report_text)
			with open(filename, "w", encoding="utf-8") as f:
					f.write(html_content)
			logger.info(f"HTML отчёт сохранён: {filename}")
		except Exception as e:
			logger.error(f"Ошибка экспорта HTML: {e}")

	def add_document(self, vector: list[float], payload: dict):
		"""Добавление документа в базу знаний."""
		self.vector_db.insert_vector(vector, payload)

	def search_documents(self, query_vector: list[float], top_k: int = 5, filters: Optional[Dict] = None):
		"""Поиск релевантных документов с фильтрацией."""
		if filters:
			return self.vector_db.search_with_filter(query_vector, filters, top_k)
		return self.vector_db.search(query_vector, top_k)

	def get_stats(self) -> Dict:
		"""Метрики для Prometheus/Grafana."""
		avg_time = self.total_time / self.requests_count if self.requests_count else 0
		return {
			"requests_count": self.requests_count,
			"avg_response_time": avg_time,
			"points_count": self.vector_db.count_points()
		}
