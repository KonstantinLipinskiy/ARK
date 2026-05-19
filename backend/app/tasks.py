from app.celery_app import celery_app
from app.db.session import get_session
from app.services.exchange import update_ohlcv_for_all_pairs
from app.utils.logger import logger
import asyncio

@celery_app.task
def update_ohlcv_task(timeframe="1h"):
	async def run():
		async with get_session() as session:
			await update_ohlcv_for_all_pairs(session, timeframe=timeframe, limit=500)
			logger.info(f"✅ OHLCV обновлены для всех пар ({timeframe})")
	asyncio.run(run())
