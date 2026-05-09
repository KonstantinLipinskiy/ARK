# app/workers/worker_backtest.py
import asyncio
import json
import pandas as pd
from app.services.backtest import backtest_strategy, calculate_metrics, save_trades_to_db, save_metrics_to_db, plot_backtest
from app.services.strategy_service import load_strategies
from app.db.session import get_session
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger

class BacktestWorker:
	"""
	Воркер для запуска бэктестов через RabbitMQ.
	Слушает очередь, принимает задачи и выполняет бэктесты асинхронно.
	"""

	def __init__(self, queue_name: str = "backtest_queue"):
		self.queue_name = queue_name
		self.broker = RabbitMQBroker()

	async def process_message(self, message: dict):
		"""
		Обработка одного сообщения из очереди.
		message должен содержать:
		{
			"pair": "BTC/USDT",
			"strategies": [...],
			"data_file": "data/BTCUSDT_1h.csv"
		}
		"""
		try:
			pair = message.get("pair")
			strategies = message.get("strategies", [])
			data_file = message.get("data_file")

			if not pair or not data_file or not strategies:
					logger.error(f"❌ Invalid backtest message: {message}")
					return

			df = pd.read_csv(data_file)
			tasks = []

			async with get_session() as session:
					for strategy in strategies:
						strategy_name = strategy.get("name", "default")

						async def run_single_backtest(strategy=strategy, strategy_name=strategy_name, df=df.copy()):
							results = await backtest_strategy(df, pair, strategy, session=session)
							metrics = calculate_metrics(results)

							await save_trades_to_db(results, pair, strategy_name=strategy_name)
							await save_metrics_to_db(metrics, pair, strategy_name=strategy_name)

							logger.info(f"✅ Backtest completed for {pair} ({strategy_name}) — {metrics}")

							# Визуализация (по желанию, можно отключить в продакшене)
							try:
									plot_backtest(df, results, pair, strategy_name)
							except Exception as e:
									logger.error(f"Ошибка визуализации {pair} ({strategy_name}): {e}")

						tasks.append(run_single_backtest())

					# Запускаем все бэктесты параллельно
					await asyncio.gather(*tasks)

		except Exception as e:
			logger.error(f"❌ BacktestWorker error: {e}")

	async def start(self):
		"""
		Запуск воркера: слушает очередь RabbitMQ и обрабатывает задачи.
		"""
		logger.info(f"🚀 BacktestWorker started, listening on queue: {self.queue_name}")
		await self.broker.consume(
			queue_name=self.queue_name,
			callback=lambda msg: asyncio.create_task(self.process_message(json.loads(msg)))
		)

if __name__ == "__main__":
	worker = BacktestWorker()
	try:
		asyncio.run(worker.start())
	except KeyboardInterrupt:
		logger.info("🛑 BacktestWorker stopped manually")
	except Exception as e:
		logger.error(f"❌ Fatal error in BacktestWorker: {e}")
