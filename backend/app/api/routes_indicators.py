# app/api/routes_indicators.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db import crud
from app.broker.rabbitmq import broker  # ⚡ используем глобальный объект
from app.cache.redis import redis_client  # ⚡ используем глобальный объект Redis
from app.services.indicator_factory import IndicatorFactory
from app.utils.logger import (
	logger,
	log_order_error,
)
from app.utils.security import get_current_user
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

@router.post("/calculate")
async def calculate_indicator(
	task: IndicatorTask,
	current_user: dict = Depends(get_current_user)
):
	"""
	Кладёт задачу расчёта индикатора в очередь RabbitMQ и пишет статус в Redis.
	"""
	try:
		IndicatorFactory.validate_indicator(task.indicator)

		task_id = str(uuid.uuid4())
		payload = {
			"task_id": task_id,
			"pair": task.pair,
			"indicator": task.indicator,
			"kwargs": task.kwargs,
			"user_id": current_user["user_id"]
		}

		start_time = time.time()

		# ⚡ используем глобальный broker, который уже подключён в lifespan
		await broker.publish_indicator(payload)

		# ⚡ используем глобальный redis_client
		await redis_client.set_task_status(task_id, "queued")

		indicators_tasks_total.inc()
		indicators_queue_time.observe(time.time() - start_time)

		return {"status": "queued", "task_id": task_id, "task": payload}

	except ValueError as e:
		indicators_tasks_errors.inc()
		log_order_error("indicator_validation", e)
		raise HTTPException(status_code=400, detail=str(e))
	except Exception as e:
		indicators_tasks_errors.inc()
		log_order_error("enqueue_indicator_task", e)
		raise HTTPException(status_code=500, detail="Failed to enqueue indicator task")

@router.get("/{pair}")
async def get_indicators(pair: str, db: AsyncSession = Depends(get_db)):
	"""
	Получает рассчитанные значения индикаторов из БД по торговой паре.
	"""
	try:
		indicators = await crud.get_indicators(db, pair=pair)
		return indicators
	except Exception as e:
		log_order_error("get_indicators", e)
		raise HTTPException(status_code=500, detail="Failed to fetch indicators")

@router.get("/status/{task_id}")
async def get_indicator_status(task_id: str):
	"""
	Возвращает состояние задачи индикатора из Redis.
	"""
	try:
		# ⚡ используем глобальный redis_client
		status = await redis_client.get_task_status(task_id)
		if not status:
			raise HTTPException(status_code=404, detail="Task not found")
		return {"task_id": task_id, "status": status}
	except Exception as e:
		log_order_error("get_indicator_status", e)
		raise HTTPException(status_code=500, detail="Failed to fetch task status")
