from app.celery_app import celery_app
from app.db.session import get_session
from app.services.exchange import update_ohlcv_for_all_pairs, get_ticker, get_order_book
from app.services.risk import RiskService
from app.utils.logger import logger
import asyncio

# --- OHLCV обновление ---
@celery_app.task
def update_ohlcv_task(timeframe="1h"):
	async def run():
		async with get_session() as session:
			await update_ohlcv_for_all_pairs(session, timeframe=timeframe, limit=500)
			logger.info(f"✅ OHLCV обновлены для всех пар ({timeframe})")
	asyncio.run(run())

# --- Funding Rate обновление ---
@celery_app.task
def update_funding_rate_task(symbol: str):
	async def run():
		async with get_session() as session:
			risk_service = RiskService(session)
			await risk_service.save_funding_rate(symbol)
	asyncio.run(run())

# --- Мониторинг тикеров ---
@celery_app.task
def monitor_ticker_task(symbol: str):
	async def run():
		ticker = await get_ticker(symbol)
		if "error" not in ticker:
			logger.info(f"📊 {symbol} Ticker: Last={ticker['last']} Bid={ticker['bid']} Ask={ticker['ask']} Spread={ticker['spread']}")
		else:
			logger.error(f"❌ Ошибка получения тикера для {symbol}: {ticker['error']}")
	asyncio.run(run())

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
	asyncio.run(run())
