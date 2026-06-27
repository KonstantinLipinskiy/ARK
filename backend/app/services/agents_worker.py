#app/services/agents_worker.py
import asyncio
import time
from app.services.agents import AgentsService
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger
from app.utils.metrics import AGENT_REQUESTS, AGENT_ERRORS, AGENT_LATENCY

class AgentsWorker:
	def __init__(self):
		# RabbitMQ брокер
		self.broker = RabbitMQBroker()
		# AgentsService без лишних параметров — всё читается из config.py
		self.agents_service = AgentsService()

	async def process_message(self, body: dict):
		"""Обработка входящего запроса агента."""
		start_time = time.time()
		try:
			query = body.get("query")
			user_id = body.get("user_id")
			output_format = body.get("output_format", "text")  # text | json | markdown | html

			logger.info(f"📥 Получен запрос агента: {query} (user_id={user_id}, format={output_format})")
			AGENT_REQUESTS.inc()

			# Вызов агента — run_agent синхронный, поэтому без await
			if isinstance(query, dict) and query.get("type") == "report":
				trades = query.get("trades", [])
				result = self.agents_service.generate_report(trades, output_format=output_format)
			else:
				result = self.agents_service.run_agent(query)

			latency = time.time() - start_time  # ⚡ latency в секундах
			AGENT_LATENCY.observe(latency)

			response_payload = {
				"type": "agent_response",
				"user_id": user_id,
				"query": query,
				"result": result,
				"latency": latency
			}
			# ⚡ публикация ответа в очередь telegram_notifications через publish_telegram
			await self.broker.publish_telegram(response_payload)
			logger.info(
				f"📤 Ответ агента отправлен пользователю {user_id}, формат={output_format}, результат={str(result)[:100]}..."
			)

		except Exception as e:
			latency = time.time() - start_time  # фиксируем время даже при ошибке
			AGENT_LATENCY.observe(latency)
			AGENT_ERRORS.inc()
			logger.error(f"❌ Ошибка обработки агента: {e}")
			error_payload = {
				"type": "agent_error",
				"error": str(e),
				"query": body.get("query", "-"),
				"user_id": body.get("user_id", None),
				"latency": latency
			}
			# ⚡ публикация ошибки также в telegram_notifications
			await self.broker.publish_telegram(error_payload)

	async def start(self):
		"""Запуск воркера: подключение к RabbitMQ и прослушивание очереди agents_queue."""
		await self.broker.connect()
		try:
			await self.broker.consume_agents(
				callback=lambda payload: asyncio.create_task(self.process_message(payload))
			)
		finally:
			await self.broker.close()
			logger.info("🔌 AgentsWorker stopped, RabbitMQ connection closed")

async def main():
	worker = AgentsWorker()
	await worker.start()

if __name__ == "__main__":
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		logger.info("🛑 AgentsWorker stopped manually")
	except Exception as e:
		logger.error(f"❌ Fatal error in AgentsWorker: {e}")
