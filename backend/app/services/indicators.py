# app/services/indicators.py
import pandas as pd
import numpy as np
from numba import njit

def validate_series(series: pd.Series, period: int) -> bool:
	"""Проверка, что серия достаточной длины и не пустая."""
	return series is not None and len(series.dropna()) >= period

# EMA (Exponential Moving Average)
def ema(series: pd.Series, period: int = 14) -> pd.Series:
	if not validate_series(series, period):
		return pd.Series(dtype=float)
	return series.ewm(span=period, adjust=False).mean()

# RSI (Relative Strength Index)
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
	if not validate_series(series, period):
		return pd.Series(dtype=float)
	delta = series.diff()
	gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
	loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
	rs = gain / loss.replace(0, np.nan)
	return 100 - (100 / (1 + rs))

# MACD (Moving Average Convergence Divergence)
def macd(series: pd.Series, short: int = 12, long: int = 26, signal: int = 9):
	if not validate_series(series, long):
		return pd.Series(dtype=float), pd.Series(dtype=float)
	ema_short = ema(series, short)
	ema_long = ema(series, long)
	macd_line = ema_short - ema_long
	signal_line = macd_line.ewm(span=signal, adjust=False).mean()
	return macd_line, signal_line

# Bollinger Bands
def bollinger(series: pd.Series, period: int = 20, std_dev: float = 2):
	if not validate_series(series, period):
		return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
	sma = series.rolling(window=period).mean()
	std = series.rolling(window=period).std()
	upper_band = sma + (std_dev * std)
	lower_band = sma - (std_dev * std)
	return upper_band, sma, lower_band

# ---------- Numba оптимизация ----------

@njit
def _atr_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
	tr = np.empty(len(close))
	tr[0] = high[0] - low[0]
	for i in range(1, len(close)):
		tr1 = high[i] - low[i]
		tr2 = abs(high[i] - close[i - 1])
		tr3 = abs(low[i] - close[i - 1])
		tr[i] = max(tr1, tr2, tr3)
	return tr

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
	if not validate_series(close, period):
		return pd.Series(dtype=float)
	tr = _atr_numba(high.values, low.values, close.values)
	return pd.Series(tr, index=close.index).rolling(window=period).mean()

@njit
def _obv_numba(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
	obv = np.zeros(len(close))
	for i in range(1, len(close)):
		if close[i] > close[i - 1]:
			obv[i] = obv[i - 1] + volume[i]
		elif close[i] < close[i - 1]:
			obv[i] = obv[i - 1] - volume[i]
		else:
			obv[i] = obv[i - 1]
	return obv

def obv(close: pd.Series, volume: pd.Series):
	if not validate_series(close, 2):
		return pd.Series(dtype=float)
	obv_values = _obv_numba(close.values, volume.values)
	return pd.Series(obv_values, index=close.index)

# Stochastic Oscillator
def stochastic(close: pd.Series, high: pd.Series, low: pd.Series, period: int = 14):
	if not validate_series(close, period):
		return pd.Series(dtype=float)
	lowest_low = low.rolling(window=period).min()
	highest_high = high.rolling(window=period).max()
	return 100 * (close - lowest_low) / (highest_high - lowest_low)

# Volume SMA (Simple Moving Average of Volume)
def volume_sma(volume: pd.Series, period: int = 20):
	if not validate_series(volume, period):
		return pd.Series(dtype=float)
	return volume.rolling(window=period).mean()

# VWAP (Volume Weighted Average Price)
def vwap(close: pd.Series, volume: pd.Series):
	if not validate_series(close, 2):
		return pd.Series(dtype=float)
	cum_vol = volume.cumsum()
	cum_vol_price = (close * volume).cumsum()
	return cum_vol_price / cum_vol.replace(0, np.nan)

# Ichimoku Cloud
def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series):
	if not validate_series(close, 52):
		return (
			pd.Series(dtype=float),
			pd.Series(dtype=float),
			pd.Series(dtype=float),
			pd.Series(dtype=float),
			pd.Series(dtype=float),
		)
	conversion_line = (high.rolling(9).max() + low.rolling(9).min()) / 2
	base_line = (high.rolling(26).max() + low.rolling(26).min()) / 2
	leading_span_a = ((conversion_line + base_line) / 2).shift(26)
	leading_span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
	lagging_span = close.shift(-26)
	return conversion_line, base_line, leading_span_a, leading_span_b, lagging_span
