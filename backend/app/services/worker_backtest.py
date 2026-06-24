#app/services/worker_backtest.py
import asyncio
import json
import pandas as pd
from app.services.backtest import (
	backtest_strategy,
	calculate_metrics,
	save_trades_to_db,
	save_metrics_to_db,
	plot_backtest
)
from app.services.ml import MLService
from app.db.session import get_session
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger
from app.db import crud
from app.config import settings


ml_service = MLService()
ml_service.load_model(path=settings.MODEL_PATH, model_type=settings.MODEL_TYPE)

class BacktestWorker:
	def __init__(self, queue_name: str = "backtest_queue"):
		self.queue_name = queue_name
		self.broker = RabbitMQBroker()

	async def process_message(self, message: dict):
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
						try:
							results = await backtest_strategy(df, pair, strategy)
							metrics = calculate_metrics(results)

							# 🔹 сохраняем сделки и метрики с Enum‑значениями
							await save_trades_to_db(results, pair, strategy_name=strategy_name, session=session)
							await save_metrics_to_db(metrics, pair, strategy_name=strategy_name, session=session)

							try:
								df_trades = pd.DataFrame(results)
								if not df_trades.empty:
									df_trades["result"] = (df_trades["exit"] - df_trades["entry"]).apply(
										lambda x: 1 if x > 0 else 0
									)
									train_metrics = ml_service.train(df_trades, model_type=settings.MODEL_TYPE)
									ml_service.save_model(settings.MODEL_PATH)
									logger.info(f"🤖 ML обучение завершено для {pair} ({strategy_name}): {train_metrics}")
							except Exception as e:
								logger.error(f"❌ Ошибка обучения ML: {e}")
								await crud.create_risk_log(session, {"reason": f"ML training failed: {e}", "symbol": pair})

							logger.info(f"✅ Backtest completed for {pair} ({strategy_name}) — {metrics}")

							if settings.DEBUG_EXPORT:
								try:
									plot_backtest(df, results, pair, strategy_name)
								except Exception as e:
									logger.error(f"Ошибка визуализации {pair} ({strategy_name}): {e}")
									await crud.create_risk_log(session, {"reason": f"Plot failed: {e}", "symbol": pair})

						except Exception as e:
							logger.error(f"❌ Ошибка бэктеста для {pair} ({strategy_name}): {e}")
							await crud.create_risk_log(session, {"reason": f"Backtest failed: {e}", "symbol": pair})

					tasks.append(run_single_backtest())

				await asyncio.gather(*tasks)

		except Exception as e:
			logger.error(f"❌ BacktestWorker error: {e}")

	async def start(self):
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
