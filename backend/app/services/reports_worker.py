# app/workers/reports_worker.py
import asyncio
import json
import time
from app.services.reports import ReportsService
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger
from app.utils.metrics import REPORT_REQUESTS_TOTAL, REPORT_AVG_RESPONSE_TIME

class ReportsWorker:
	def __init__(self, collection_name: str = "trades"):
		self.broker = RabbitMQBroker()
		self.reports_service = ReportsService(collection_name=collection_name)
		self.queue_name = "queue_reports"

	async def start(self):
		"""Запуск воркера: подключение к RabbitMQ и прослушивание очереди."""
		await self.broker.connect()
		await self.broker.channel.queue_declare(queue=self.queue_name, durable=True)
		await self.broker.channel.basic_consume(self.queue_name, self.handle_message, auto_ack=False)
		logger.info("🚀 ReportsWorker запущен и слушает очередь queue_reports")

	async def handle_message(self, message):
		"""Обработка входящего запроса на генерацию отчёта."""
		start_time = time.time()
		try:
			body = json.loads(message.body.decode())
			trades = body.get("trades", [])
			filters = body.get("filters")
			user_id = body.get("user_id")
			export_format = body.get("export_format", "text")  # text, json, markdown, html, pdf

			logger.info(f"📥 Получен запрос на отчёт (user_id={user_id}, format={export_format})")
			REPORT_REQUESTS_TOTAL.inc()

			# Генерация отчёта с пробросом формата
			report_text = self.reports_service.generate_rag_report(
				trades,
				filters=filters,
				output_format=export_format if export_format in ["text", "json", "markdown", "html"] else "text"
			)

			# Экспорт в PDF/HTML при необходимости
			if export_format == "pdf":
				filename = f"report_{user_id}.pdf"
				self.reports_service.export_report_pdf(report_text, filename)
				result = {"status": "ok", "file": filename}
			elif export_format == "html":
				filename = f"report_{user_id}.html"
				self.reports_service.export_report_html(report_text, filename)
				result = {"status": "ok", "file": filename}
			else:
				result = {"status": "ok", "report": report_text}

			# Метрики времени ответа
			duration = time.time() - start_time
			self.reports_service.total_time += duration
			REPORT_AVG_RESPONSE_TIME.set(self.reports_service.total_time / self.reports_service.requests_count)

			# Публикация результата в очередь Telegram
			response_payload = {
				"type": "report_response",
				"user_id": user_id,
				"result": result,
				"latency": duration
			}
			await self.broker.publish_telegram(response_payload)
			await message.ack()
			logger.info(f"📤 Отчёт отправлен пользователю {user_id}, формат={export_format}")

		except Exception as e:
			logger.error(f"❌ Ошибка генерации отчёта: {e}")
			error_payload = {
				"type": "report_error",
				"error": str(e),
				"user_id": body.get("user_id", None)
			}
			await self.broker.publish_telegram(error_payload)
			await message.ack()

async def main():
	worker = ReportsWorker(collection_name="trades")
	await worker.start()

if __name__ == "__main__":
	asyncio.run(main())
