import pandas as pd
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
		# расширенные индикаторы
		"Stochastic": indicators.stochastic,
		"VolumeSMA": indicators.volume_sma,
		"VWAP": indicators.vwap,
		"Ichimoku": indicators.ichimoku,
	}

	@classmethod
	def calculate(cls, name: str, **kwargs):
		"""
		Унифицированный вызов индикатора.
		Пример: IndicatorFactory.calculate("EMA", series=close, period=14)
		"""
		if name not in cls._registry:
			logger.error(f"❌ Unknown indicator: {name}")
			raise ValueError(f"❌ Unknown indicator: {name}")
		func = cls._registry[name]

		# Валидация входных данных
		cls._validate_inputs(kwargs)

		try:
			return func(**kwargs)
		except Exception as e:
			logger.error(f"❌ Error calculating {name}: {e}")
			raise RuntimeError(f"❌ Error calculating {name}: {e}")

	@staticmethod
	def _validate_inputs(kwargs: dict):
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
