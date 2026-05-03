import os
import asyncio
from aiogram import Bot
from dotenv import load_dotenv
from app.utils.logger import logger
from app.services.rabbitmq import RabbitMQBroker  # твой класс брокера

# Загружаем токен и chat_id из .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)
broker = RabbitMQBroker()

async def process_notification(message: str):
	"""
	Обработка уведомления из очереди RabbitMQ.
	message: строка (JSON или dict в виде строки)
	"""
	logger.info(f"📨 Telegram worker получил сообщение: {message}")
	try:
		# Можно парсить JSON, если будешь публиковать payload как json.dumps()
		await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
	except Exception as e:
		logger.error(f"❌ Ошибка отправки в Telegram: {e}")

async def consume_notifications():
	"""Подключение к RabbitMQ и прослушивание очереди telegram_notifications."""
	await broker.connect()
	await broker.consume_telegram(process_notification)

async def main():
	logger.info("🚀 Запуск Telegram воркера...")
	try:
		await consume_notifications()
	finally:
		await broker.close()
		await bot.session.close()
		logger.info("🔌 Telegram воркер остановлен")

if __name__ == "__main__":
	asyncio.run(main())
