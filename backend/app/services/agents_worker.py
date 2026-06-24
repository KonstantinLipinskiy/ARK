import asyncio
import json
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
		self.queue_name = "queue_agents"

	async def start(self):
		"""Запуск воркера: подключение к RabbitMQ и прослушивание очереди."""
		await self.broker.connect()
		await self.broker.channel.queue_declare(queue=self.queue_name, durable=True)
		await self.broker.channel.basic_consume(self.queue_name, self.handle_message, auto_ack=False)
		logger.info("🚀 AgentsWorker запущен и слушает очередь queue_agents")

	async def handle_message(self, message):
		"""Обработка входящего запроса агента."""
		start_time = time.time()
		try:
			body = json.loads(message.body.decode())
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

			latency = time.time() - start_time
			AGENT_LATENCY.observe(latency)

			response_payload = {
				"type": "agent_response",
				"user_id": user_id,
				"query": query,
				"result": result,
				"latency": latency
			}
			await self.broker.publish("queue_telegram", response_payload)
			await message.ack()
			logger.info(
				f"📤 Ответ агента отправлен пользователю {user_id}, формат={output_format}, результат={str(result)[:100]}..."
			)

		except Exception as e:
			AGENT_ERRORS.inc()
			logger.error(f"❌ Ошибка обработки агента: {e}")
			error_payload = {
				"type": "agent_error",
				"error": str(e),
				"query": body.get("query", "-"),
				"user_id": body.get("user_id", None)
			}
			await self.broker.publish("queue_telegram", error_payload)
			await message.ack()

async def main():
	worker = AgentsWorker()
	await worker.start()

if __name__ == "__main__":
	asyncio.run(main())
