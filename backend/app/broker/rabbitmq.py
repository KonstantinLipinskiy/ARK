# app/broker/rabbitmq.py
import asyncio
import aio_pika
import logging
from app.utils.logger import logger
from app.config import RABBITMQ_CONFIG

class RabbitMQBroker:
	def __init__(self,
					host: str = RABBITMQ_CONFIG["host"],
					queue_signals: str = RABBITMQ_CONFIG["queue_signals"],
					queue_trades: str = RABBITMQ_CONFIG["queue_trades"]):
		self.host = host
		self.queue_signals = queue_signals
		self.queue_trades = queue_trades
		self.connection = None
		self.channel = None


	async def connect(self):
		"""Асинхронное подключение к RabbitMQ."""
		try:
			self.connection = await aio_pika.connect_robust(self.host)
			self.channel = await self.connection.channel()
			await self.channel.declare_queue(self.queue_signals, durable=True)
			await self.channel.declare_queue(self.queue_trades, durable=True)
			logger.info("✅ RabbitMQ connected")
		except Exception as e:
			logger.error(f"❌ RabbitMQ connection error: {e}")
			raise

	async def publish_signal(self, signal: dict):
		"""Отправка торгового сигнала в очередь."""
		try:
			await self.channel.default_exchange.publish(
					aio_pika.Message(
						body=str(signal).encode(),
						delivery_mode=aio_pika.DeliveryMode.PERSISTENT
					),
					routing_key=self.queue_signals
			)
			logger.debug(f"📤 Signal published: {signal}")
		except Exception as e:
			logger.error(f"❌ Failed to publish signal: {e}")

	async def publish_trade(self, trade: dict):
		"""Отправка сделки в очередь."""
		try:
			await self.channel.default_exchange.publish(
					aio_pika.Message(
						body=str(trade).encode(),
						delivery_mode=aio_pika.DeliveryMode.PERSISTENT
					),
					routing_key=self.queue_trades
			)
			logger.debug(f"📤 Trade published: {trade}")
		except Exception as e:
			logger.error(f"❌ Failed to publish trade: {e}")

	async def consume_signals(self, callback):
		"""Получение сигналов из очереди."""
		try:
			queue = await self.channel.declare_queue(self.queue_signals, durable=True)
			async with queue.iterator() as q:
					async for message in q:
						async with message.process():
							try:
									await callback(message.body.decode())
							except Exception as e:
									logger.error(f"❌ Error processing signal: {e}")
		except Exception as e:
			logger.error(f"❌ Failed to consume signals: {e}")

	async def consume_trades(self, callback):
		"""Получение сделок из очереди."""
		try:
			queue = await self.channel.declare_queue(self.queue_trades, durable=True)
			async with queue.iterator() as q:
					async for message in q:
						async with message.process():
							try:
									await callback(message.body.decode())
							except Exception as e:
									logger.error(f"❌ Error processing trade: {e}")
		except Exception as e:
			logger.error(f"❌ Failed to consume trades: {e}")

	async def close(self):
		"""Закрывает соединение."""
		if self.connection:
			await self.connection.close()
			logger.info("🔌 RabbitMQ connection closed")
