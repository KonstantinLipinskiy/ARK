# app/api/routes/indicators.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.logger import logger

router = APIRouter()

class IndicatorTask(BaseModel):
	pair: str
	indicator: str
	kwargs: dict

@router.post("/indicators/calculate")
async def calculate_indicator(task: IndicatorTask):
	"""
	Кладёт задачу расчёта индикатора в очередь RabbitMQ.
	Воркер потом её подхватит и выполнит расчёт.
	"""
	try:
		broker = RabbitMQBroker()
		await broker.connect()

		payload = {
			"pair": task.pair,
			"indicator": task.indicator,
			"kwargs": task.kwargs
		}

		await broker.publish_indicator(payload)
		await broker.close()

		return {"status": "queued", "task": payload}

	except Exception as e:
		logger.error(f"❌ Failed to enqueue indicator task: {e}")
		return {"status": "error", "message": str(e)}
