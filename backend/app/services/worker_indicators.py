import asyncio
import json
from app.services.indicators_service import IndicatorsService
from app.db.session import async_session
from app.cache.redis import RedisCache
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger

class IndicatorWorker:
	"""
	Воркер для обработки задач расчёта индикаторов через RabbitMQ.
	Слушает очередь, выполняет расчёт и сохраняет результат.
	"""

	def __init__(self, queue_name: str = "indicators_queue"):
		self.queue_name = queue_name
		self.broker = RabbitMQBroker()

	async def process_message(self, message: dict):
		"""
		Обработка одного сообщения из очереди.
		"""
		try:
			pair = message.get("pair")
			indicator = message.get("indicator")
			kwargs = message.get("kwargs", {})

			async with async_session() as session:
					redis = RedisCache()
					service = IndicatorsService(session, redis)
					await service.calculate_and_store(pair, indicator, **kwargs)

			logger.info(f"✅ Indicator {indicator} for {pair} calculated and stored")

		except Exception as e:
			logger.error(f"❌ Worker error: {e}")

	async def start(self):
		"""
		Запуск воркера: слушает очередь RabbitMQ и обрабатывает задачи.
		"""
		await self.broker.consume(
			queue_name=self.queue_name,
			callback=lambda msg: asyncio.create_task(self.process_message(json.loads(msg)))
		)

if __name__ == "__main__":
	worker = IndicatorWorker()
	asyncio.run(worker.start())

