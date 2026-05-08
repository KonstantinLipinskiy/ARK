# app/broker/rabbitmq.py
import asyncio
import aio_pika
from app.utils.logger import logger
from app.config import RABBITMQ_CONFIG

class RabbitMQBroker:
	def __init__(self,
					host: str = RABBITMQ_CONFIG["host"],
					queue_signals: str = RABBITMQ_CONFIG["queue_signals"],
					queue_trades: str = RABBITMQ_CONFIG["queue_trades"],
					queue_indicators: str = RABBITMQ_CONFIG.get("queue_indicators", "indicators_queue"),
					queue_telegram: str = RABBITMQ_CONFIG.get("queue_telegram", "telegram_notifications")):
		self.host = host
		self.queue_signals = queue_signals
		self.queue_trades = queue_trades
		self.queue_indicators = queue_indicators
		self.queue_telegram = queue_telegram
		self.connection = None
		self.channel = None

	async def connect(self):
		"""Асинхронное подключение к RabbitMQ."""
		try:
			self.connection = await aio_pika.connect_robust(self.host)
			self.channel = await self.connection.channel()
			await self.channel.declare_queue(self.queue_signals, durable=True)
			await self.channel.declare_queue(self.queue_trades, durable=True)
			await self.channel.declare_queue(self.queue_indicators, durable=True)
			await self.channel.declare_queue(self.queue_telegram, durable=True)
			logger.info("✅ RabbitMQ connected and queues declared")
		except Exception as e:
			logger.error(f"❌ RabbitMQ connection error: {e}")
			raise

	async def publish_signal(self, signal: dict):
		"""Отправка торгового сигнала в очередь."""
		await self._publish(self.queue_signals, signal, "Signal")

	async def publish_trade(self, trade: dict):
		"""Отправка сделки в очередь."""
		await self._publish(self.queue_trades, trade, "Trade")

	async def publish_indicator(self, payload: dict):
		"""Отправка задачи расчёта индикатора в очередь."""
		await self._publish(self.queue_indicators, payload, "Indicator task")

	async def publish_telegram(self, payload: dict):
		"""Отправка уведомления в очередь Telegram."""
		await self._publish(self.queue_telegram, payload, "Telegram notification")

	async def _publish(self, queue_name: str, payload: dict, label: str):
		"""Унифицированная публикация сообщений."""
		try:
			await self.channel.default_exchange.publish(
					aio_pika.Message(
						body=str(payload).encode(),
						delivery_mode=aio_pika.DeliveryMode.PERSISTENT
					),
					routing_key=queue_name
			)
			logger.debug(f"📤 {label} published: {payload}")
		except Exception as e:
			logger.error(f"❌ Failed to publish {label}: {e}")

	async def consume_signals(self, callback):
		"""Получение сигналов из очереди."""
		await self._consume(self.queue_signals, callback, "Signal")

	async def consume_trades(self, callback):
		"""Получение сделок из очереди."""
		await self._consume(self.queue_trades, callback, "Trade")

	async def consume_indicators(self, callback):
		"""Получение задач индикаторов из очереди."""
		await self._consume(self.queue_indicators, callback, "Indicator task")

	async def consume_telegram(self, callback):
		"""Получение уведомлений из очереди Telegram."""
		await self._consume(self.queue_telegram, callback, "Telegram notification")

	async def _consume(self, queue_name: str, callback, label: str):
		"""Унифицированное получение сообщений из очереди."""
		try:
			queue = await self.channel.declare_queue(queue_name, durable=True)
			async with queue.iterator() as q:
					async for message in q:
						async with message.process():
							try:
									await callback(message.body.decode())
									logger.debug(f"📥 {label} consumed: {message.body.decode()}")
							except Exception as e:
									logger.error(f"❌ Error processing {label}: {e}")
		except Exception as e:
			logger.error(f"❌ Failed to consume {label}: {e}")

	async def close(self):
		"""Закрывает соединение."""
		if self.connection:
			await self.connection.close()
			logger.info("🔌 RabbitMQ connection closed")
