import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Импортируем наш общий логгер
from app.utils.logger import logger
from app.db.schemas import TradeORM, SignalORM
from app.config import STRATEGY_CONFIG, RISK_CONFIG
from app.services.rabbitmq import RabbitMQBroker
from app.utils.metrics import calculate_metrics

# Загружаем токен и chat_id из .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
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


telegram_service = TelegramService(bot, TELEGRAM_CHAT_ID)
broker = RabbitMQBroker()

# --- Команды ---
@dp.message(Command("start"))
async def start_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		logger.warning(f"Попытка доступа от чужого chat_id: {message.chat.id}")
		return
	logger.info("Выполнена команда /start")
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и статистику.")

@dp.message(Command("status"))
async def status_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /status")
	async with AsyncSession() as session:
		result = await session.execute(select(TradeORM).where(TradeORM.status == "open"))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([f"{t.symbol} {t.side} {t.amount} @ {t.price}" for t in trades])
			await message.answer(f"📌 Активные позиции:\n{msg}")
		else:
			await message.answer("Пока нет открытых позиций.")

@dp.message(Command("trades"))
async def trades_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /trades")
	async with AsyncSession() as session:
		result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp.desc()).limit(10))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([f"{t.symbol} {t.side} {t.amount} @ {t.price} ({t.status})" for t in trades])
			await message.answer(f"📊 Последние сделки:\n{msg}")
		else:
			await message.answer("История сделок пуста.")


@dp.message(Command("report"))
async def report_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /report")
	async with AsyncSession() as session:
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
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /config")
	await message.answer(f"⚙️ Текущие настройки стратегии:\n{STRATEGY_CONFIG}")

@dp.message(Command("risk"))
async def risk_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /risk")
	await message.answer(f"📉 Лимиты риск менеджмента:\n{RISK_CONFIG}")

@dp.message(Command("signal"))
async def signal_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /signal")
	async with AsyncSession() as session:
		result = await session.execute(select(SignalORM).order_by(SignalORM.timestamp.desc()).limit(5))
		signals = result.scalars().all()
		if signals:
			msg = "\n".join([f"{s.symbol} {s.action} @ {s.price}" for s in signals])
			await message.answer(f"📡 Последние сигналы:\n{msg}")
		else:
			await message.answer("Сигналы отсутствуют.")

@dp.message(Command("help"))
async def help_command(message: types.Message):
	logger.info("Выполнена команда /help")
	await message.answer(
		"📖 Доступные команды:\n"
		"/start — запуск бота\n"
		"/status — активные позиции\n"
		"/trades — история сделок\n"
		"/report — отчёт по метрикам\n"
		"/config — настройки стратегии\n"
		"/risk — лимиты риск менеджмента\n"
		"/signal — последние торговые сигналы\n"
		"/id — показать ваш chat_id\n"
		"/help — список команд"
	)

@dp.message(Command("id"))
async def get_id(message: types.Message):
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
