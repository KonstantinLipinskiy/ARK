#app/services/indicators_service.py
import asyncio
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.indicator_factory import IndicatorFactory
from app.db.schemas import IndicatorORM
from app.utils.logger import logger
from app.cache.redis import RedisCache

class IndicatorsService:
	"""
	Сервисный слой для работы с индикаторами:
	- Валидация входных данных
	- Асинхронные вызовы
	- Сохранение результатов в БД
	- Интеграция с Redis pub/sub
	"""

	def __init__(self, db_session: AsyncSession, redis: RedisCache):
		self.db_session = db_session
		self.redis = redis

	async def calculate_and_store(self, pair: str, indicator_name: str, **kwargs):
		"""
		Асинхронный расчёт индикатора и сохранение результата в БД + Redis.
		"""
		try:
			self._validate_inputs(kwargs)

			result = await IndicatorFactory.calculate_async(indicator_name, **kwargs)

			await self._save_to_db(pair, indicator_name, result)

			await self._publish_to_redis(pair, indicator_name, result)

			logger.info(f"✅ Indicator {indicator_name} успешно рассчитан и сохранён | Параметры: {kwargs}")
			return result

		except Exception as e:
			logger.error(f"❌ Error in IndicatorsService.calculate_and_store: {e} | Параметры: {kwargs}")
			return None

	async def _save_to_db(self, pair: str, indicator_name: str, result, retries: int = 2):
		"""
		Сохраняет рассчитанный индикатор в таблицу indicators.
		Добавлен retry при временных ошибках.
		"""
		attempt = 0
		while attempt <= retries:
			try:
					if isinstance(result, tuple):
						values = []
						for idx, res in enumerate(result):
							val = res.iloc[-1] if isinstance(res, pd.Series) else str(res)
							indicator = IndicatorORM(
									pair=pair,
									name=f"{indicator_name}_{idx}",
									value=str(val)
							)
							self.db_session.add(indicator)
							values.append(val)
						await self.db_session.commit()
						logger.info(f"✅ DB save: {indicator_name} → {values}")
					else:
						value = result.iloc[-1] if isinstance(result, pd.Series) else str(result)
						indicator = IndicatorORM(
							pair=pair,
							name=indicator_name,
							value=str(value)
						)
						self.db_session.add(indicator)
						await self.db_session.commit()
						logger.info(f"✅ DB save: {indicator_name} → {value}")
					return
			except Exception as e:
					logger.error(f"❌ DB save error (attempt {attempt+1}): {e}")
					await self.db_session.rollback()
					attempt += 1
					if attempt > retries:
						logger.error(f"❌ DB save failed after {retries+1} attempts for {indicator_name}")
						return
					await asyncio.sleep(1) 

	async def _publish_to_redis(self, pair: str, indicator_name: str, result, retries: int = 2):
		"""
		Публикует результат в Redis канал indicators.
		Добавлен retry при временных ошибках.
		"""
		attempt = 0
		while attempt <= retries:
			try:
					if isinstance(result, tuple):
						payload = {
							"pair": pair,
							"indicator": indicator_name,
							"result": [
									res.tail(1).to_dict() if isinstance(res, pd.Series) else str(res)
									for res in result
							]
						}
					else:
						payload = {
							"pair": pair,
							"indicator": indicator_name,
							"result": (
									result.tail(1).to_dict()
									if isinstance(result, pd.Series)
									else str(result)
							)
						}
					await self.redis.publish("indicators", payload)
					logger.info(f"✅ Redis publish: {indicator_name} → {payload}")
					return
			except Exception as e:
					logger.error(f"❌ Redis publish error (attempt {attempt+1}): {e}")
					attempt += 1
					if attempt > retries:
						logger.error(f"❌ Redis publish failed after {retries+1} attempts for {indicator_name}")
						return
					await asyncio.sleep(1)

	def _validate_inputs(self, kwargs: dict):
		"""
		Проверка входных данных: серии не пустые, достаточная длина, нет NaN.
		"""
		for key, value in kwargs.items():
			if isinstance(value, pd.Series):
					if value.empty:
						raise ValueError(f"❌ Series {key} is empty")
					if value.isna().all():
						raise ValueError(f"❌ Series {key} contains only NaN")
					if len(value) < 5:
						raise ValueError(f"❌ Series {key} too short for calculation")

		if "period" in kwargs:
			period = kwargs["period"]
			if not isinstance(period, int) or period <= 0:
					raise ValueError(f"❌ Invalid period value: {period}. Must be int > 0")
