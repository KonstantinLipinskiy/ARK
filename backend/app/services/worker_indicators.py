# app/workers/worker_indicators.py
import asyncio
import json
import time
from app.services.indicators_service import IndicatorsService
from app.db.session import async_session
from app.cache.redis import RedisCache
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger
from app.services.ml import MLService

class IndicatorWorker:
	"""
	Воркер для обработки задач расчёта индикаторов и обучения ML через RabbitMQ.
	Слушает очередь, выполняет расчёт и сохраняет результат.
	"""

	def __init__(self, queue_name: str = "indicators_queue"):
		self.queue_name = queue_name
		self.broker = RabbitMQBroker()
		self.ml_service = MLService()

	async def process_message(self, message: dict):
		"""
		Обработка одного сообщения из очереди.
		"""
		try:
			task_type = message.get("task_type", "indicator")
			pair = message.get("pair")
			indicator = message.get("indicator")
			kwargs = message.get("kwargs", {})

			start_time = time.time()

			if task_type == "indicator":
					if not pair or not indicator:
						logger.error(f"❌ Invalid indicator message: {message}")
						return

					async with async_session() as session:
						redis = RedisCache()
						service = IndicatorsService(session, redis)
						# heavy calc вынесен в отдельный таск (async)
						result = await service.calculate_and_store(pair, indicator, **kwargs)

					elapsed = round(time.time() - start_time, 3)
					if result is not None:
						logger.info(
							f"✅ Indicator {indicator} for {pair} calculated and stored "
							f"(elapsed {elapsed}s, params={kwargs})"
						)
					else:
						logger.error(
							f"❌ Indicator {indicator} for {pair} failed "
							f"(elapsed {elapsed}s, params={kwargs})"
						)

			elif task_type == "ml_train":
					trades = message.get("trades", [])
					model_type = message.get("model_type", "sklearn")

					if not trades:
						logger.error("❌ ML training skipped: empty trades")
						return

					try:
						df = self.ml_service.prepare_data(trades)
						metrics = self.ml_service.train(df, model_type=model_type)
						elapsed = round(time.time() - start_time, 3)
						logger.info(
							f"🤖 ML training completed for {pair} ({model_type}) "
							f"in {elapsed}s: {metrics}"
						)
					except Exception as e:
						logger.error(f"❌ ML training error: {e} | trades={len(trades)}")

			else:
					logger.error(f"❌ Unknown task type: {task_type}")

		except Exception as e:
			logger.error(f"❌ Worker error: {e} | message={message}")

	async def start(self):
		"""
		Запуск воркера: слушает очередь RabbitMQ и обрабатывает задачи.
		"""
		logger.info(f"🚀 IndicatorWorker started, listening on queue: {self.queue_name}")
		await self.broker.consume(
			queue_name=self.queue_name,
			callback=lambda msg: asyncio.create_task(self.process_message(json.loads(msg)))
		)

if __name__ == "__main__":
	worker = IndicatorWorker()
	try:
		asyncio.run(worker.start())
	except KeyboardInterrupt:
		logger.info("🛑 IndicatorWorker stopped manually")
	except Exception as e:
		logger.error(f"❌ Fatal error in IndicatorWorker: {e}")
