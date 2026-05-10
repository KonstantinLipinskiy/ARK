# app/broker/rabbitmq.py
import asyncio
import aio_pika
import time
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
					queue_reports: str = RABBITMQ_CONFIG.get("queue_reports", "reports_queue"),
					queue_alerts: str = RABBITMQ_CONFIG.get("queue_alerts", "alerts_queue"),
					queue_logs: str = RABBITMQ_CONFIG.get("queue_logs", "logs_queue"),
					exchange_type: str = RABBITMQ_CONFIG.get("exchange_type", "direct")):
		self.host = host
		self.queue_signals = queue_signals
		self.queue_trades = queue_trades
		self.queue_indicators = queue_indicators
		self.queue_telegram = queue_telegram
		self.queue_backtest = queue_backtest
		self.queue_agents = queue_agents
		self.queue_reports = queue_reports
		self.queue_alerts = queue_alerts
		self.queue_logs = queue_logs
		self.exchange_type = exchange_type
		self.connection = None
		self.channel = None
		self.exchange = None

		# --- Метрики ---
		self.messages_published = 0
		self.messages_consumed = 0
		self.errors_total = 0
		self.processing_times = []

	async def connect(self):
		"""Асинхронное подключение к RabbitMQ и объявление всех очередей."""
		try:
			self.connection = await aio_pika.connect_robust(self.host)
			self.channel = await self.connection.channel()

			# Exchange (direct, fanout, topic)
			self.exchange = await self.channel.declare_exchange(
					"app_exchange", type=self.exchange_type, durable=True
			)

			# Очереди
			for q in [
					self.queue_signals, self.queue_trades, self.queue_indicators,
					self.queue_telegram, self.queue_backtest, self.queue_agents,
					self.queue_reports, self.queue_alerts, self.queue_logs
			]:
					await self.channel.declare_queue(q, durable=True)
					await self.exchange.bind(q, routing_key=q)

			logger.info("✅ RabbitMQ connected, exchange declared and queues bound")
		except Exception as e:
			self.errors_total += 1
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

	async def publish_alert(self, payload: dict):
		await self._publish(self.queue_alerts, payload, "Alert")

	async def publish_log(self, payload: dict):
		await self._publish(self.queue_logs, payload, "Log")

	async def _publish(self, queue_name: str, payload: dict, label: str, retries: int = 3):
		attempt = 0
		while attempt <= retries:
			try:
					start = time.time()
					await self.exchange.publish(
						aio_pika.Message(
							body=str(payload).encode(),
							delivery_mode=aio_pika.DeliveryMode.PERSISTENT
						),
						routing_key=queue_name
					)
					elapsed = round(time.time() - start, 3)
					self.messages_published += 1
					self.processing_times.append(elapsed)
					logger.debug(f"📤 {label} published: {payload} (elapsed {elapsed}s)")
					return
			except Exception as e:
					self.errors_total += 1
					attempt += 1
					logger.error(f"❌ Failed to publish {label} (attempt {attempt}): {e}")
					if attempt > retries:
						logger.error(f"❌ Publish {label} failed after {retries+1} attempts")
						return
					await asyncio.sleep(2 ** attempt)  # экспоненциальная задержка

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

	async def consume_alerts(self, callback):
		await self._consume(self.queue_alerts, callback, "Alert")

	async def consume_logs(self, callback):
		await self._consume(self.queue_logs, callback, "Log")

	async def _consume(self, queue_name: str, callback, label: str, retries: int = 3):
		attempt = 0
		while attempt <= retries:
			try:
					queue = await self.channel.declare_queue(queue_name, durable=True)
					async with queue.iterator() as q:
						async for message in q:
							async with message.process():
									try:
										start = time.time()
										await callback(message.body.decode())
										elapsed = round(time.time() - start, 3)
										self.messages_consumed += 1
										self.processing_times.append(elapsed)
										logger.debug(f"📥 {label} consumed: {message.body.decode()} (elapsed {elapsed}s)")
									except Exception as e:
										self.errors_total += 1
										logger.error(f"❌ Error processing {label}: {e}")
					return
			except Exception as e:
					self.errors_total += 1
					attempt += 1
					logger.error(f"❌ Failed to consume {label} (attempt {attempt}): {e}")
					if attempt > retries:
						logger.error(f"❌ Consume {label} failed after {retries+1} attempts")
						return
					await asyncio.sleep(2 ** attempt)

	async def close(self):
		if self.connection:
			await self.connection.close()
			logger.info("🔌 RabbitMQ connection closed")

	# --- Метрики ---
	def get_metrics(self) -> dict:
		"""Возвращает базовые метрики для мониторинга."""
		return {
			"messages_published": self.messages_published,
			"messages_consumed": self.messages_consumed,
			"errors_total": self.errors_total,
			"avg_processing_time": round(sum(self.processing_times) / len(self.processing_times), 3)
			if self.processing_times else 0
		}
