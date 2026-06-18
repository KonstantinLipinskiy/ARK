# scripts/fetch_data.py
import ccxt
import pandas as pd
import datetime
import os

# список пар для загрузки
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT"]

def update_csv(symbol: str, timeframe="1h", days=60, out_dir="data"):
	exchange = ccxt.binance()
	since = exchange.parse8601((datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat())
	ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)

	df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
	df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

	# имя файла: BTCUSDT_1h.csv
	filename = f"{symbol.replace('/', '')}_{timeframe}.csv"
	filepath = os.path.join(out_dir, filename)
	df.to_csv(filepath, index=False)

	print(f"✅ Updated {filepath} with {len(df)} rows")

if __name__ == "__main__":
	os.makedirs("data", exist_ok=True)
	for pair in PAIRS:
		update_csv(pair, timeframe="1h", days=60)
