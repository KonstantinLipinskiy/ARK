import pika

class RabbitMQBroker:
	def __init__(self, host: str = "localhost", queue_signals: str = "signals", queue_trades: str = "trades"):
		self.host = host
		self.queue_signals = queue_signals
		self.queue_trades = queue_trades
		self.connection = None
		self.channel = None

	def connect(self):
		"""Устанавливает соединение с RabbitMQ."""
		self.connection = pika.BlockingConnection(pika.ConnectionParameters(self.host))
		self.channel = self.connection.channel()
		# Объявляем очереди
		self.channel.queue_declare(queue=self.queue_signals, durable=True)
		self.channel.queue_declare(queue=self.queue_trades, durable=True)

	def publish_signal(self, signal: dict):
		"""Отправка торгового сигнала в очередь."""
		self.channel.basic_publish(
			exchange="",
			routing_key=self.queue_signals,
			body=str(signal),
			properties=pika.BasicProperties(delivery_mode=2)  # сохраняем сообщение
		)

	def publish_trade(self, trade: dict):
		"""Отправка сделки в очередь."""
		self.channel.basic_publish(
			exchange="",
			routing_key=self.queue_trades,
			body=str(trade),
			properties=pika.BasicProperties(delivery_mode=2)
		)

	def consume_signals(self, callback):
		"""Получение сигналов из очереди."""
		self.channel.basic_consume(queue=self.queue_signals, on_message_callback=callback, auto_ack=True)
		self.channel.start_consuming()

	def consume_trades(self, callback):
		"""Получение сделок из очереди."""
		self.channel.basic_consume(queue=self.queue_trades, on_message_callback=callback, auto_ack=True)
		self.channel.start_consuming()

	def close(self):
		"""Закрывает соединение."""
		if self.connection:
			self.connection.close()