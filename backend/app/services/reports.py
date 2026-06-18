# app/services/reports.py
import time
from typing import List, Dict, Optional
from langchain_community.chains import RetrievalQA   # новый вариант
from langchain_openai import OpenAI
from app.db.vector import VectorDB
from app.utils.metrics import calculate_metrics
from app.services.ml import MLService
from app.utils.logger import logger
from prometheus_client import Counter, Gauge
import pandas as pd
from fpdf import FPDF
from jinja2 import Template
import json

# 🔹 Метрики Prometheus
REPORT_REQUESTS_TOTAL = Counter("report_requests_total", "Total RAG report requests")
REPORT_AVG_RESPONSE_TIME = Gauge("report_avg_response_time", "Average response time for RAG reports")

class ReportsService:
	def __init__(self, collection_name: str = "trades"):
		self.llm = OpenAI(temperature=0)
		self.vector_db = VectorDB(collection_name=collection_name)
		self.qa_chain = RetrievalQA.from_chain_type(
			llm=self.llm,
			retriever=self.vector_db.client.as_retriever(),
			chain_type="stuff"
		)
		self.ml = MLService()
		self.requests_count = 0
		self.total_time = 0.0

	def use_collection(self, name: str):
		self.vector_db.use_collection(name)

	def generate_report(self, query: str) -> str:
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
		limit: int = 100,
		output_format: str = "text"  # text | json | markdown
	) -> str:
		"""Комплексный RAG-отчёт с метриками, ML прогнозами и сравнением стратегий/пользователей.
		🔹 Добавлена фильтрация: исключаем тестовые трейды и нерелевантные документы.
		🔹 Поддержка форматов: text, json, markdown.
		"""
		self.requests_count += 1
		REPORT_REQUESTS_TOTAL.inc()
		start = time.time()

		# 🔹 Фильтрация трейдов: исключаем тестовые и пустые
		trades = [t for t in trades if not t.get("test", False) and t.get("action") in ["buy", "sell"]]

		metrics = calculate_metrics(trades)

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

		search_results = []
		try:
			query_vector = [0.0] * 768
			if filters:
				search_results = self.vector_db.search_with_filter(query_vector, filters, limit)
			else:
				search_results = self.vector_db.search(query_vector, limit)

			# 🔹 Фильтрация документов: исключаем нерелевантные
			search_results = [
				doc for doc in search_results
				if not doc.get("payload", {}).get("irrelevant", False)
			]
		except Exception as e:
			logger.error(f"Ошибка поиска документов для отчёта: {e}")

		comparison_summary = []
		try:
			df = pd.DataFrame(trades)
			if not df.empty and "user_id" in df.columns and "strategy" in df.columns:
				grouped = df.groupby(["user_id", "strategy"]).apply(lambda g: calculate_metrics(g.to_dict("records")))
				for (user, strat), m in grouped.items():
					comparison_summary.append({
						"user_id": user,
						"strategy": strat,
						"winrate": m["winrate"],
						"profit": m["total_profit"]
					})
		except Exception as e:
			logger.error(f"Ошибка сравнения стратегий/пользователей: {e}")

		# --- Форматирование ---
		if output_format == "json":
			report = json.dumps({
				"metrics": metrics,
				"ml_summary": ml_summary,
				"documents_found": len(search_results),
				"comparison": comparison_summary
			}, ensure_ascii=False, indent=2)
		elif output_format == "markdown":
			report = f"""# 📊 RAG Отчёт

**Всего сделок:** {metrics['trades_count']}  
**Winrate:** {metrics['winrate']:.2%}  
**Profit:** {metrics['total_profit']:.2f}  
**Drawdown:** {metrics['max_drawdown']:.2f}  
**Sharpe:** {metrics['sharpe_ratio']:.2f}  
**Sortino:** {metrics['sortino_ratio']:.2f}  
**Profit Factor:** {metrics['profit_factor']:.2f}  
**Макс. серия побед:** {metrics['max_consecutive_wins']}  
**Макс. серия поражений:** {metrics['max_consecutive_losses']}  

{ml_summary}  

🔎 **Найдено документов:** {len(search_results)}  

## Сравнение стратегий и пользователей
""" + "\n".join([
				f"- 👤 User {c['user_id']}, Strategy {c['strategy']}: Winrate={c['winrate']:.2%}, Profit={c['profit']:.2f}"
				for c in comparison_summary
			])
		else:
			# текстовый отчёт
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
				f"Сравнение стратегий и пользователей:\n" +
				"\n".join([
					f"👤 User {c['user_id']}, Strategy {c['strategy']}: Winrate={c['winrate']:.2%}, Profit={c['profit']:.2f}"
					for c in comparison_summary
				])
			)

		duration = time.time() - start
		self.total_time += duration
		REPORT_AVG_RESPONSE_TIME.set(self.total_time / self.requests_count)
		return report

	def export_report_pdf(self, report_text: str, filename: str = "report.pdf"):
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
		self.vector_db.insert_vector(vector, payload)

	def search_documents(self, query_vector: list[float], top_k: int = 5, filters: Optional[Dict] = None):
		if filters:
			return self.vector_db.search_with_filter(query_vector, filters, top_k)
		return self.vector_db.search(query_vector, top_k)

	def get_stats(self) -> Dict:
		"""
		Получить статистику по отчётам и векторной базе.
		"""
		avg_time = self.total_time / self.requests_count if self.requests_count else 0
		return {
			"requests_count": self.requests_count,
			"avg_response_time": avg_time,
			"points_count": self.vector_db.count_points()
		}
