# app/workers/agents_worker.py
import asyncio
import json
import time
from app.services.agents import AgentsService
from app.services.rabbitmq import RabbitMQBroker
from app.utils.logger import logger
from app.utils.metrics import AGENT_REQUESTS, AGENT_ERRORS, AGENT_LATENCY

class AgentsWorker:
	def __init__(self, llm_provider: str = "openai"):
		self.broker = RabbitMQBroker()
		self.agents_service = AgentsService(llm_provider=llm_provider, temperature=0.2, top_p=0.9, max_tokens=512)
		self.queue_name = "queue_agents"

	async def start(self):
		await self.broker.connect()
		await self.broker.channel.queue_declare(queue=self.queue_name, durable=True)
		await self.broker.channel.basic_consume(self.queue_name, self.handle_message, auto_ack=False)
		logger.info("🚀 AgentsWorker запущен и слушает очередь queue_agents")

	async def handle_message(self, message):
		start_time = time.time()
		try:
			body = json.loads(message.body.decode())
			query = body.get("query")
			user_id = body.get("user_id")

			logger.info(f"📥 Получен запрос агента: {query} (user_id={user_id})")
			AGENT_REQUESTS.inc()

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
			logger.info(f"📤 Ответ агента отправлен: {result[:100]}...")

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
	worker = AgentsWorker(llm_provider="openai")
	await worker.start()

if __name__ == "__main__":
	asyncio.run(main())
