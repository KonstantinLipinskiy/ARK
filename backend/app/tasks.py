# app/tasks.py
from app.celery_app import celery_app
from app.db.session import get_session
from app.services.exchange import update_ohlcv_for_all_pairs, get_ticker, get_order_book
from app.services.risk import RiskService
from app.utils.logger import logger
import asyncio
from app.services.news_loader import NewsLoader
from app.config import settings
from app.db import crud
from scripts.fetch_data import update_csv
import subprocess

# --- Вспомогательная функция для запуска async-кода ---
def run_async(coro):
	try:
		loop = asyncio.get_event_loop()
	except RuntimeError:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
	return loop.run_until_complete(coro)

# --- OHLCV обновление ---
@celery_app.task
def update_ohlcv_task(timeframe="1h"):
	async def run():
		async with get_session() as session:
			await update_ohlcv_for_all_pairs(session, timeframe=timeframe, limit=500)
			logger.info(f"✅ OHLCV обновлены для всех пар ({timeframe})")
	run_async(run())

# --- Funding Rate обновление ---
@celery_app.task
def update_funding_rate_task(symbol: str):
	async def run():
		async with get_session() as session:
			risk_service = RiskService(session)
			await risk_service.save_funding_rate(symbol)
	run_async(run())

# --- Мониторинг тикеров ---
@celery_app.task
def monitor_ticker_task(symbol: str):
	async def run():
		ticker = await get_ticker(symbol)
		if "error" not in ticker:
			logger.info(f"📊 {symbol} Ticker: Last={ticker['last']} Bid={ticker['bid']} Ask={ticker['ask']} Spread={ticker['spread']}")
		else:
			logger.error(f"❌ Ошибка получения тикера для {symbol}: {ticker['error']}")
	run_async(run())

# --- Мониторинг стакана ---
@celery_app.task
def monitor_order_book_task(symbol: str):
	async def run():
		order_book = await get_order_book(symbol, limit=20)
		if "error" not in order_book:
			total_bids = sum([b[1] for b in order_book["bids"]])
			total_asks = sum([a[1] for a in order_book["asks"]])
			imbalance = total_bids - total_asks
			logger.info(f"📊 {symbol} OrderBook: Bids={total_bids:.2f} Asks={total_asks:.2f} Imbalance={imbalance:.2f}")
		else:
			logger.error(f"❌ Ошибка получения стакана для {symbol}: {order_book['error']}")
	run_async(run())

# --- Новости ---
@celery_app.task
def fetch_crypto_news_task(pair="BTC/USDT"):
	async def run():
		symbol = pair.split("/")[0].lower()

		loader = NewsLoader(newsdata_api_key=settings.NEWSDATA_API_KEY)
		news = loader.fetch_newsdata(query=symbol)
		rss = loader.fetch_coindesk_rss()

		# Фильтрация RSS по ключевому слову монеты
		filtered_rss = [n for n in rss if symbol.upper() in n or symbol.capitalize() in n]

		all_news = news + filtered_rss
		if all_news:
			logger.info(f"📰 Получено {len(all_news)} новостей для {pair}")

			# ✅ сохраняем в БД
			async with get_session() as session:
				for item in all_news:
					try:
						await crud.create_news(
							session,
							symbol=symbol.upper(),
							title=item.get("title"),
							content=item.get("content", ""),
							source=item.get("source", "unknown"),
							published_at=item.get("published_at")
						)
					except Exception as e:
						logger.error(f"❌ Ошибка сохранения новости: {e}")
		else:
			logger.warning(f"⚠️ Новости для {pair} не получены")

	run_async(run())

# --- Обновление CSV (fetch_data) ---
@celery_app.task
def update_csv_task(timeframe: str = settings.DEFAULT_TIMEFRAME,
					days: int = settings.DEFAULT_DAYS,
					out_dir: str = settings.DATA_DIR):
	"""
	Celery таск для обновления CSV файлов OHLCV по всем парам.
	"""
	try:
		for pair in settings.PAIRS:
			update_csv(pair, timeframe=timeframe, days=days, out_dir=out_dir)
		logger.info(f"✅ CSV обновлены для всех пар ({timeframe}, {days} дней)")
	except Exception as e:
		logger.error(f"❌ Ошибка обновления CSV: {e}")

# --- Запуск Backtest ---
@celery_app.task
def run_backtest_task():
	"""
	Celery таск для запуска backtest.py.
	Выполняется каждое воскресенье в 03:00.
	"""
	try:
		result = subprocess.run(
			["python", "backtest.py"],
			capture_output=True,
			text=True
		)
		if result.returncode == 0:
			logger.info(f"✅ Backtest успешно завершён:\n{result.stdout}")
		else:
			logger.error(f"❌ Ошибка выполнения backtest.py:\n{result.stderr}")
	except Exception as e:
		logger.error(f"❌ Ошибка запуска backtest.py: {e}")
