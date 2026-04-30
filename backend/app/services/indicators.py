import pandas as pd
import numpy as np

# EMA (Exponential Moving Average)
def ema(series: pd.Series, period: int = 14) -> pd.Series:
	return series.ewm(span=period, adjust=False).mean()

# RSI (Relative Strength Index)
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
	delta = series.diff()
	gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
	loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
	rs = gain / loss
	return 100 - (100 / (1 + rs))

# MACD (Moving Average Convergence Divergence)
def macd(series: pd.Series, short: int = 12, long: int = 26, signal: int = 9):
	ema_short = ema(series, short)
	ema_long = ema(series, long)
	macd_line = ema_short - ema_long
	signal_line = macd_line.ewm(span=signal, adjust=False).mean()
	return macd_line, signal_line

# Bollinger Bands
def bollinger(series: pd.Series, period: int = 20, std_dev: float = 2):
	sma = series.rolling(window=period).mean()
	std = series.rolling(window=period).std()
	upper_band = sma + (std_dev * std)
	lower_band = sma - (std_dev * std)
	return upper_band, sma, lower_band

# ATR (Average True Range)
def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
	tr1 = high - low
	tr2 = abs(high - close.shift())
	tr3 = abs(low - close.shift())
	tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
	return tr.rolling(window=period).mean()

# OBV (On-Balance Volume)
def obv(close: pd.Series, volume: pd.Series):
	obv = [0]
	for i in range(1, len(close)):
		if close[i] > close[i - 1]:
			obv.append(obv[-1] + volume[i])
		elif close[i] < close[i - 1]:
			obv.append(obv[-1] - volume[i])
		else:
			obv.append(obv[-1])
	return pd.Series(obv, index=close.index)

# Stochastic Oscillator
def stochastic(close: pd.Series, high: pd.Series, low: pd.Series, period: int = 14):
	lowest_low = low.rolling(window=period).min()
	highest_high = high.rolling(window=period).max()
	return 100 * (close - lowest_low) / (highest_high - lowest_low)

# Volume SMA (Simple Moving Average of Volume)
def volume_sma(volume: pd.Series, period: int = 20):
	return volume.rolling(window=period).mean()

# VWAP (Volume Weighted Average Price)
def vwap(close: pd.Series, volume: pd.Series):
	cum_vol = volume.cumsum()
	cum_vol_price = (close * volume).cumsum()
	return cum_vol_price / cum_vol

# Ichimoku Cloud
def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series):
	conversion_line = (high.rolling(9).max() + low.rolling(9).min()) / 2
	base_line = (high.rolling(26).max() + low.rolling(26).min()) / 2
	leading_span_a = ((conversion_line + base_line) / 2).shift(26)
	leading_span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
	lagging_span = close.shift(-26)
	return conversion_line, base_line, leading_span_a, leading_span_b, lagging_span
