import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

# Загружаем токен из .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Логирование
logging.basicConfig(level=logging.INFO)

# 🔹 Команда /start
@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и статистику.")

# 🔹 Команда /status
@dp.message_handler(commands=["status"])
async def status_command(message: types.Message):
	# Здесь можно подтянуть текущие активные позиции из базы
	await message.answer("Пока нет открытых позиций.")  # пример

# 🔹 Команда /trades
@dp.message_handler(commands=["trades"])
async def trades_command(message: types.Message):
	# Здесь можно подтянуть историю сделок
	await message.answer("История сделок будет доступна позже.")  # пример

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
	await bot.send_message(chat_id=YOUR_CHAT_ID, text=msg)

# 🔹 Запуск бота
if __name__ == "__main__":
	executor.start_polling(dp, skip_updates=True)
