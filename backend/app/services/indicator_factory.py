# app/services/indicator_factory.py
import pandas as pd
import inspect
import asyncio
from app.services import indicators
from app.utils.logger import logger

class IndicatorFactory:
	"""
	Унифицированный интерфейс для вызова индикаторов по имени.
	Работает через STRATEGY_CONFIG.
	"""

	_registry = {
		"EMA": indicators.ema,
		"RSI": indicators.rsi,
		"MACD": indicators.macd,
		"Bollinger": indicators.bollinger,
		"ATR": indicators.atr,
		"OBV": indicators.obv,
		"Stochastic": indicators.stochastic,
		"VolumeSMA": indicators.volume_sma,
		"VWAP": indicators.vwap,
		"Ichimoku": indicators.ichimoku,
	}

	@classmethod
	def supported_indicators(cls) -> list[str]:
		"""
		Возвращает список поддерживаемых индикаторов.
		"""
		return list(cls._registry.keys())

	@classmethod
	def validate_indicator(cls, name: str):
		"""
		Проверяет, что индикатор поддерживается.
		"""
		if name not in cls._registry:
			logger.error(
				f"❌ Unsupported indicator requested: {name}",
				extra={"operation": "indicator", "collection": name}
			)
			raise ValueError(f"❌ Unsupported indicator: {name}. Supported: {cls.supported_indicators()}")

	@classmethod
	def register(cls, name: str, func):
		"""
		Добавление нового индикатора в фабрику.
		Пример: IndicatorFactory.register("Custom", custom_func)
		"""
		if name in cls._registry:
			logger.warning(
				f"⚠️ Indicator {name} уже существует и будет перезаписан",
				extra={"operation": "indicator", "collection": name}
			)
		cls._registry[name] = func
		logger.info(
			f"✅ Indicator {name} зарегистрирован",
			extra={"operation": "indicator", "collection": name}
		)

	@classmethod
	def calculate(cls, name: str, **kwargs):
		"""
		Унифицированный вызов индикатора (синхронный).
		Пример: IndicatorFactory.calculate("EMA", series=close, period=14)
		"""
		cls.validate_indicator(name)
		func = cls._registry[name]

		cls._validate_inputs(kwargs)

		try:
			result = func(**kwargs)
			logger.info(
				f"✅ Indicator {name} рассчитан | Параметры: {kwargs}",
				extra={"operation": "indicator", "collection": name}
			)
			return result
		except Exception as e:
			logger.error(
				f"❌ Error calculating {name}: {e} | Параметры: {kwargs}",
				extra={"operation": "indicator", "collection": name}
			)
			raise RuntimeError(f"❌ Error calculating {name}: {e}")

	@classmethod
	async def calculate_async(cls, name: str, **kwargs):
		"""
		Асинхронный вызов индикатора.
		Если функция синхронная — выполняется в отдельном потоке.
		"""
		cls.validate_indicator(name)
		func = cls._registry[name]

		cls._validate_inputs(kwargs)

		try:
			if inspect.iscoroutinefunction(func):
				result = await func(**kwargs)
			else:
				loop = asyncio.get_event_loop()
				result = await loop.run_in_executor(None, lambda: func(**kwargs))
			logger.info(
				f"✅ Indicator {name} рассчитан (async) | Параметры: {kwargs}",
				extra={"operation": "indicator", "collection": name}
			)
			return result
		except Exception as e:
			logger.error(
				f"❌ Async error calculating {name}: {e} | Параметры: {kwargs}",
				extra={"operation": "indicator", "collection": name}
			)
			raise RuntimeError(f"❌ Async error calculating {name}: {e}")

	@staticmethod
	def _validate_inputs(kwargs: dict):
		"""
		Проверка входных данных: серии не пустые, достаточная длина, нет NaN,
		а также базовая проверка параметров (например, period > 0).
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
