import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

# Импортируем наш общий логгер
from app.utils.logger import logger

# Загружаем токен и chat_id из .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# 🔹 Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		logger.warning(f"Попытка доступа от чужого chat_id: {message.chat.id}")
		return
	logger.info("Выполнена команда /start")
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и статистику.")

# 🔹 Команда /status
@dp.message(Command("status"))
async def status_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /status")
	await message.answer("Пока нет открытых позиций.")  # пример

# 🔹 Команда /trades
@dp.message(Command("trades"))
async def trades_command(message: types.Message):
	if str(message.chat.id) != TELEGRAM_CHAT_ID:
		return
	logger.info("Выполнена команда /trades")
	await message.answer("История сделок будет доступна позже.")  # пример

# 🔹 Команда /id (для получения chat_id)
@dp.message(Command("id"))
async def get_id(message: types.Message):
	logger.info(f"Запрос chat_id от пользователя {message.chat.id}")
	await message.answer(f"Ваш chat_id: {message.chat.id}")

# 🔹 Функция для отправки уведомлений из других модулей
async def send_trade_notification(trade: dict):
	"""
	trade: словарь с данными сделки
	"""
	msg = (
		f"📊 Сделка по {trade.get('pair', 'N/A')}\n"
		f"Статус: {trade['status']}\n"
		f"Вход: {trade['entry']}\n"
		f"Выход: {trade.get('exit', '-')}\n"
		f"TP: {trade.get('tp', '-')}\n"
		f"SL: {trade.get('stop', '-')}"
	)
	logger.info(f"Отправка уведомления: {msg.replace(os.linesep, ' ')}")
	await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

# 🔹 Запуск бота (aiogram v3)
async def main():
	logger.info("Запуск Telegram бота...")
	try:
		await dp.start_polling(bot)
	finally:
		await bot.session.close()
		logger.info("Сессия Telegram бота закрыта")

if __name__ == "__main__":
	asyncio.run(main())



# if __name__ == "__main__":
# 	asyncio.run(send_trade_notification({
# 		"pair": "BTC/USDT",
# 		"status": "open",
# 		"entry": "65000",
# 		"exit": None,
# 		"tp": "67000",
# 		"stop": "64000"
# 	}))
