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
					queue_telegram: str = RABBITMQ_CONFIG.get("queue_telegram", "telegram_notifications"),
					queue_backtest: str = RABBITMQ_CONFIG.get("queue_backtest", "backtest_queue"),
					queue_agents: str = RABBITMQ_CONFIG.get("queue_agents", "agents_queue"),
					queue_reports: str = RABBITMQ_CONFIG.get("queue_reports", "reports_queue")):
		self.host = host
		self.queue_signals = queue_signals
		self.queue_trades = queue_trades
		self.queue_indicators = queue_indicators
		self.queue_telegram = queue_telegram
		self.queue_backtest = queue_backtest
		self.queue_agents = queue_agents
		self.queue_reports = queue_reports
		self.connection = None
		self.channel = None

	async def connect(self):
		"""Асинхронное подключение к RabbitMQ и объявление всех очередей."""
		try:
			self.connection = await aio_pika.connect_robust(self.host)
			self.channel = await self.connection.channel()
			await self.channel.declare_queue(self.queue_signals, durable=True)
			await self.channel.declare_queue(self.queue_trades, durable=True)
			await self.channel.declare_queue(self.queue_indicators, durable=True)
			await self.channel.declare_queue(self.queue_telegram, durable=True)
			await self.channel.declare_queue(self.queue_backtest, durable=True)
			await self.channel.declare_queue(self.queue_agents, durable=True)
			await self.channel.declare_queue(self.queue_reports, durable=True)
			logger.info("✅ RabbitMQ connected and queues declared")
		except Exception as e:
			logger.error(f"❌ RabbitMQ connection error: {e}")
			raise

	# --- Публикация сообщений ---
	async def publish_signal(self, signal: dict):
		await self._publish(self.queue_signals, signal, "Signal")

	async def publish_trade(self, trade: dict):
		await self._publish(self.queue_trades, trade, "Trade")

	async def publish_indicator(self, payload: dict):
		await self._publish(self.queue_indicators, payload, "Indicator task")

	async def publish_telegram(self, payload: dict):
		await self._publish(self.queue_telegram, payload, "Telegram notification")

	async def publish_backtest(self, payload: dict):
		await self._publish(self.queue_backtest, payload, "Backtest task")

	async def publish_agent(self, payload: dict):
		await self._publish(self.queue_agents, payload, "Agent task")

	async def publish_report(self, payload: dict):
		await self._publish(self.queue_reports, payload, "Report task")

	async def _publish(self, queue_name: str, payload: dict, label: str):
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

	# --- Получение сообщений ---
	async def consume_signals(self, callback):
		await self._consume(self.queue_signals, callback, "Signal")

	async def consume_trades(self, callback):
		await self._consume(self.queue_trades, callback, "Trade")

	async def consume_indicators(self, callback):
		await self._consume(self.queue_indicators, callback, "Indicator task")

	async def consume_telegram(self, callback):
		await self._consume(self.queue_telegram, callback, "Telegram notification")

	async def consume_backtest(self, callback):
		await self._consume(self.queue_backtest, callback, "Backtest task")

	async def consume_agents(self, callback):
		await self._consume(self.queue_agents, callback, "Agent task")

	async def consume_reports(self, callback):
		await self._consume(self.queue_reports, callback, "Report task")

	async def _consume(self, queue_name: str, callback, label: str):
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
		if self.connection:
			await self.connection.close()
			logger.info("🔌 RabbitMQ connection closed")
