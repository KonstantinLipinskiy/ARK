import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from sqlalchemy import select

# Импортируем наш общий логгер
from app.utils.logger import logger
from app.db.schemas import TradeORM, SignalORM
from app.services.rabbitmq import RabbitMQBroker
from app.utils.metrics import calculate_metrics
from app.config import Settings
from app.db.session import get_session
from app.services.strategy_service import load_strategies
from app.services.risk import RiskService

settings = Settings()
bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

# --- TelegramService для использования в risk.py и orders.py ---
class TelegramService:
	def __init__(self, bot: Bot, chat_id: str):
		self.bot = bot
		self.chat_id = chat_id

	async def send_message(self, text: str):
		logger.info(f"Отправка сообщения в Telegram: {text}")
		await self.bot.send_message(chat_id=self.chat_id, text=text)

	async def send_trade_notification(self, trade: dict):
		msg = (
			f"📊 Сделка по {trade.get('pair', 'N/A')}\n"
			f"Статус: {trade['status']}\n"
			f"Вход: {trade['entry']}\n"
			f"Выход: {trade.get('exit', '-')}\n"
			f"TP: {trade.get('tp', '-')}\n"
			f"SL: {trade.get('stop', '-')}"
		)
		await self.send_message(msg)

	async def send_error(self, error: str):
		msg = f"❌ Ошибка: {error}"
		await self.send_message(msg)

telegram_service = TelegramService(bot, settings.TELEGRAM_CHAT_ID)
broker = RabbitMQBroker()

# --- Проверка chat_id ---
def is_authorized(message: types.Message) -> bool:
	if str(message.chat.id) != settings.TELEGRAM_CHAT_ID:
		logger.warning(f"Попытка доступа от чужого chat_id: {message.chat.id}")
		return False
	return True

# --- Команды ---
@dp.message(Command("start"))
async def start_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /start")
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и статистику.")

@dp.message(Command("status"))
async def status_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /status")
	async with get_session() as session:
		result = await session.execute(select(TradeORM).where(TradeORM.status == "open"))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([f"{t.symbol} {t.side} {t.amount} @ {t.price}" for t in trades])
			await message.answer(f"📌 Активные позиции:\n{msg}")
		else:
			await message.answer("Пока нет открытых позиций.")

@dp.message(Command("trades"))
async def trades_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /trades")
	async with get_session() as session:
		result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp.desc()).limit(10))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([f"{t.symbol} {t.side} {t.amount} @ {t.price} ({t.status})" for t in trades])
			await message.answer(f"📊 Последние сделки:\n{msg}")
		else:
			await message.answer("История сделок пуста.")

@dp.message(Command("report"))
async def report_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /report")
	async with get_session() as session:
		result = await session.execute(select(TradeORM))
		trades = result.scalars().all()
		metrics = calculate_metrics(trades)
		msg = (
			f"📊 Отчёт по стратегиям:\n"
			f"Всего сделок: {metrics['trades_count']}\n"
			f"Winrate: {metrics['winrate']:.2%}\n"
			f"Profit: {metrics['total_profit']:.2f}\n"
			f"Drawdown: {metrics['max_drawdown']:.2f}\n"
			f"Sharpe: {metrics['sharpe_ratio']:.2f}\n"
			f"Sortino: {metrics['sortino_ratio']:.2f}\n"
			f"Profit Factor: {metrics['profit_factor']:.2f}\n"
			f"Макс. серия побед: {metrics['max_consecutive_wins']}\n"
			f"Макс. серия поражений: {metrics['max_consecutive_losses']}"
		)
		await message.answer(msg)

@dp.message(Command("config"))
async def config_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /config")
	async with get_session() as session:
		strategies = await load_strategies(session)
		await message.answer(f"⚙️ Текущие настройки стратегии:\n{strategies}")

@dp.message(Command("risk"))
async def risk_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /risk")
	async with get_session() as session:
		risk_service = RiskService(db_session=session)
		await risk_service.refresh_config()
		limits = risk_service.get_limits()
		msg = (
			f"📉 Лимиты риск менеджмента:\n"
			f"Stop Loss (из стратегии): {limits.get('stop_loss_pct', '-')}\n"
			f"Default Trade Loss: {limits.get('default_trade_loss_pct', '-')}\n"
			f"Макс. количество сделок: {limits.get('max_trades', '-')}\n"
			f"Макс. плечо: {limits.get('max_leverage', '-')}"
		)
		await message.answer(msg)

@dp.message(Command("limits"))
async def limits_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /limits")
	async with get_session() as session:
		strategies = await load_strategies(session)
		msg_lines = []
		for symbol, cfg in strategies.items():
			msg_lines.append(
					f"{symbol}: Stop Loss={cfg.get('stop_loss', '-')}, Leverage={cfg.get('leverage', '-')}"
			)
		msg = "📈 Лимиты по стратегиям:\n" + "\n".join(msg_lines)
		await message.answer(msg)

@dp.message(Command("metrics"))
async def metrics_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /metrics")
	args = message.text.split()
	if len(args) < 2:
		await message.answer("❗ Использование: /metrics SYMBOL")
		return
	symbol = args[1].upper()
	async with get_session() as session:
		result = await session.execute(select(TradeORM).where(TradeORM.symbol == symbol))
		trades = result.scalars().all()
		if not trades:
			await message.answer(f"Нет сделок по {symbol}")
			return
		metrics = calculate_metrics(trades)
		msg = (
			f"📊 Отчёт по {symbol}:\n"
			f"Всего сделок: {metrics['trades_count']}\n"
			f"Winrate: {metrics['winrate']:.2%}\n"
			f"Profit: {metrics['total_profit']:.2f}\n"
			f"Drawdown: {metrics['max_drawdown']:.2f}\n"
			f"Sharpe: {metrics['sharpe_ratio']:.2f}\n"
			f"Sortino: {metrics['sortino_ratio']:.2f}\n"
			f"Profit Factor: {metrics['profit_factor']:.2f}\n"
			f"Макс. серия побед: {metrics['max_consecutive_wins']}\n"
			f"Макс. серия поражений: {metrics['max_consecutive_losses']}"
		)
		await message.answer(msg)

@dp.message(Command("signal"))
async def signal_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /signal")
	async with get_session() as session:
		result = await session.execute(select(SignalORM).order_by(SignalORM.timestamp.desc()).limit(5))
		signals = result.scalars().all()
		if signals:
			msg = "\n".join([f"{s.symbol} {s.action} @ {s.price}" for s in signals])
			await message.answer(f"📡 Последние сигналы:\n{msg}")
		else:
			await message.answer("Сигналы отсутствуют.")

@dp.message(Command("help"))
async def help_command(message: types.Message):
	if not is_authorized(message):
		return
	logger.info("Выполнена команда /help")
	await message.answer(
		"📖 Доступные команды:\n"
		"/start — запуск бота\n"
		"/status — активные позиции\n"
		"/trades — история сделок\n"
		"/report — отчёт по метрикам\n"
		"/config — настройки стратегии\n"
		"/risk — лимиты риск менеджмента\n"
		"/limits — лимиты по стратегиям\n"
		"/metrics SYMBOL — метрики по конкретному инструменту\n"
		"/signal — последние торговые сигналы\n"
		"/id — показать ваш chat_id\n"
		"/help — список команд"
	)

@dp.message(Command("id"))
async def get_id(message: types.Message):
	if not is_authorized(message):
		return
	logger.info(f"Запрос chat_id от пользователя {message.chat.id}")
	await message.answer(f"Ваш chat_id: {message.chat.id}")

# --- Запуск бота ---
async def main():
	logger.info("Запуск Telegram бота...")
	try:
		await broker.connect()  # подключение к RabbitMQ
		await dp.start_polling(bot)
	finally:
		await broker.close()
		await bot.session.close()
		logger.info("Сессия Telegram бота закрыта")

if __name__ == "__main__":
	asyncio.run(main())
