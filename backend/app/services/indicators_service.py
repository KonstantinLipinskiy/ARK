import asyncio
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.indicator_factory import IndicatorFactory
from app.db.models import Indicator  # модель таблицы indicators
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
			# Валидация входных данных
			self._validate_inputs(kwargs)

			# Расчёт индикатора
			result = IndicatorFactory.calculate(indicator_name, **kwargs)

			# Сохранение в БД
			await self._save_to_db(pair, indicator_name, result)

			# Публикация в Redis (для воркеров/уведомлений)
			await self._publish_to_redis(pair, indicator_name, result)

			return result

		except Exception as e:
			logger.error(f"❌ Error in IndicatorsService.calculate_and_store: {e}")
			return None

	async def _save_to_db(self, pair: str, indicator_name: str, result):
		"""
		Сохраняет рассчитанный индикатор в таблицу indicators.
		"""
		try:
			# Пример: сохраняем последнее значение индикатора
			value = result.iloc[-1] if isinstance(result, pd.Series) else str(result)

			indicator = Indicator(
					pair=pair,
					name=indicator_name,
					value=str(value)
			)
			self.db_session.add(indicator)
			await self.db_session.commit()
		except Exception as e:
			logger.error(f"❌ DB save error: {e}")
			await self.db_session.rollback()

	async def _publish_to_redis(self, pair: str, indicator_name: str, result):
		"""
		Публикует результат в Redis канал indicators.
		"""
		try:
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
		except Exception as e:
			logger.error(f"❌ Redis publish error: {e}")

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
