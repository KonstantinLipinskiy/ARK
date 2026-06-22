# scripts/fetch_data.py
import ccxt
import pandas as pd
import datetime
import os
import argparse
from app.utils.logger import logger
from app.config import settings

def update_csv(symbol: str, timeframe: str, days: int, out_dir: str):
	"""
	Загружает OHLCV данные для пары и сохраняет в CSV.
	"""
	try:
		exchange = ccxt.binance()
		since = exchange.parse8601(
			(datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
		)
		ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)

		if not ohlcv or len(ohlcv) == 0:
			logger.warning(f"⚠️ Нет данных для {symbol} ({timeframe}), файл не обновлён")
			return

		df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
		df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

		# имя файла: BTCUSDT_1h.csv
		filename = f"{symbol.replace('/', '')}_{timeframe}.csv"
		filepath = os.path.join(out_dir, filename)
		df.to_csv(filepath, index=False)

		logger.info(f"✅ Updated {filepath} with {len(df)} rows")

	except Exception as e:
		logger.error(f"❌ Ошибка обновления данных для {symbol} ({timeframe}): {e}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Fetch OHLCV data from Binance")
	parser.add_argument("--timeframe", type=str, default=settings.DEFAULT_TIMEFRAME, help="Таймфрейм (например, 1h, 1d)")
	parser.add_argument("--days", type=int, default=settings.DEFAULT_DAYS, help="Количество дней для загрузки")
	parser.add_argument("--out_dir", type=str, default=settings.DATA_DIR, help="Папка для сохранения CSV")
	args = parser.parse_args()

	os.makedirs(args.out_dir, exist_ok=True)

	for pair in settings.PAIRS:
		update_csv(pair, timeframe=args.timeframe, days=args.days, out_dir=args.out_dir)
