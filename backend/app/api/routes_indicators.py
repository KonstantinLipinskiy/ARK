# app/api/routes_indicators.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db import crud
from app.broker.rabbitmq import RabbitMQBroker
from app.cache.redis import RedisCache
from app.services.indicator_factory import IndicatorFactory
from app.utils.logger import logger
from app.monitoring.prometheus import (
	indicators_tasks_total,
	indicators_tasks_errors,
	indicators_task_duration,
	indicators_queue_time
)
import time
import uuid

router = APIRouter(prefix="/indicators", tags=["Indicators"])

class IndicatorTask(BaseModel):
	pair: str
	indicator: str
	kwargs: dict

# 🔹 POST /indicators/calculate
@router.post("/calculate")
async def calculate_indicator(task: IndicatorTask, request: Request):
	"""
	Кладёт задачу расчёта индикатора в очередь RabbitMQ и пишет статус в Redis.
	"""
	try:
		# Валидация индикатора
		IndicatorFactory.validate_indicator(task.indicator)

		broker = RabbitMQBroker()
		await broker.connect()

		task_id = str(uuid.uuid4())
		payload = {
			"task_id": task_id,
			"pair": task.pair,
			"indicator": task.indicator,
			"kwargs": task.kwargs,
			"user_id": getattr(request.state, "user_id", None)
		}

		# Метрики: время постановки
		start_time = time.time()

		await broker.publish_indicator(payload)
		await broker.close()

		# Записываем статус в Redis
		redis = RedisCache()
		await redis.set_task_status(task_id, "queued")

		# Метрики Prometheus
		indicators_tasks_total.inc()
		indicators_queue_time.observe(time.time() - start_time)

		return {"status": "queued", "task_id": task_id, "task": payload}

	except ValueError as e:
		indicators_tasks_errors.inc()
		logger.error(f"❌ Indicator validation error: {e}")
		raise HTTPException(status_code=400, detail=str(e))
	except Exception as e:
		indicators_tasks_errors.inc()
		logger.error(f"❌ Failed to enqueue indicator task: {e}")
		raise HTTPException(status_code=500, detail="Failed to enqueue indicator task")

# 🔹 GET /indicators/{pair}
@router.get("/{pair}")
async def get_indicators(pair: str, db: AsyncSession = Depends(get_db)):
	"""
	Получает рассчитанные значения индикаторов из БД по торговой паре.
	"""
	try:
		indicators = await crud.get_indicators(db, pair=pair)
		return indicators
	except Exception as e:
		logger.error(f"❌ Failed to fetch indicators for {pair}: {e}")
		raise HTTPException(status_code=500, detail="Failed to fetch indicators")

# 🔹 GET /indicators/status/{task_id}
@router.get("/status/{task_id}")
async def get_indicator_status(task_id: str):
	"""
	Возвращает состояние задачи индикатора из Redis.
	"""
	try:
		redis = RedisCache()
		status = await redis.get_task_status(task_id)
		if not status:
			raise HTTPException(status_code=404, detail="Task not found")
		return {"task_id": task_id, "status": status}
	except Exception as e:
		logger.error(f"❌ Failed to fetch task status: {e}")
		raise HTTPException(status_code=500, detail="Failed to fetch task status")
