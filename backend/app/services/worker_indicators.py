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
	Воркер для обработки задач расчёта индикаторов и ML через RabbitMQ.
	Поддерживает:
	- indicator: расчёт индикаторов
	- ml_train: обучение ML модели
	- ml_predict: прогнозы на основе ML модели
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
						await self.broker.publish_alert({"type": "error", "reason": "Invalid indicator message", "payload": message})
						return

					async with async_session() as session:
						redis = RedisCache()
						service = IndicatorsService(session, redis)

						result = await service.calculate_and_store(pair, indicator, **kwargs)

					elapsed = round(time.time() - start_time, 3)
					if result is not None:
						logger.info(
							f"✅ Indicator {indicator} for {pair} calculated and stored "
							f"(elapsed {elapsed}s, params={kwargs})"
						)
						await self.broker.publish_log({"type": "indicator", "pair": pair, "indicator": indicator, "elapsed": elapsed})
					else:
						logger.error(
							f"❌ Indicator {indicator} for {pair} failed "
							f"(elapsed {elapsed}s, params={kwargs})"
						)
						await self.broker.publish_alert({"type": "indicator_failed", "pair": pair, "indicator": indicator, "params": kwargs})

			elif task_type == "ml_train":
					trades = message.get("trades", [])
					model_type = message.get("model_type", "sklearn")

					if not trades:
						logger.error("❌ ML training skipped: empty trades")
						await self.broker.publish_alert({"type": "ml_train_skipped", "reason": "empty trades"})
						return

					try:
						df = self.ml_service.prepare_data(trades)
						metrics = self.ml_service.train(df, model_type=model_type)
						elapsed = round(time.time() - start_time, 3)
						logger.info(
							f"🤖 ML training completed for {pair} ({model_type}) "
							f"in {elapsed}s | metrics={metrics} | trades={len(trades)}"
						)
						await self.broker.publish_log({"type": "ml_train", "pair": pair, "model": model_type, "metrics": metrics, "elapsed": elapsed})
					except Exception as e:
						logger.error(f"❌ ML training error: {e} | trades={len(trades)}")
						await self.broker.publish_alert({"type": "ml_train_error", "error": str(e), "trades": len(trades)})

			elif task_type == "ml_predict":
					input_data = message.get("input_data", [])
					model_type = message.get("model_type", "sklearn")

					if not input_data:
						logger.error("❌ ML prediction skipped: empty input_data")
						await self.broker.publish_alert({"type": "ml_predict_skipped", "reason": "empty input_data"})
						return

					try:
						predictions = self.ml_service.predict(input_data, model_type=model_type)
						elapsed = round(time.time() - start_time, 3)
						logger.info(
							f"🔮 ML prediction completed for {pair} ({model_type}) "
							f"in {elapsed}s | predictions={predictions}"
						)
						await self.broker.publish_log({"type": "ml_predict", "pair": pair, "model": model_type, "predictions": predictions, "elapsed": elapsed})
					except Exception as e:
						logger.error(f"❌ ML prediction error: {e} | input_size={len(input_data)}")
						await self.broker.publish_alert({"type": "ml_predict_error", "error": str(e), "input_size": len(input_data)})

			else:
					logger.error(f"❌ Unknown task type: {task_type}")
					await self.broker.publish_alert({"type": "unknown_task", "task_type": task_type, "payload": message})

		except Exception as e:
			logger.error(f"❌ Worker error: {e} | message={message}")
			await self.broker.publish_alert({"type": "worker_error", "error": str(e), "payload": message})

	async def start(self):
		"""
		Запуск воркера: слушает очередь RabbitMQ и обрабатывает задачи.
		"""
		logger.info(f"🚀 IndicatorWorker started, listening on queue: {self.queue_name}")
		await self.broker.consume_indicators(
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
