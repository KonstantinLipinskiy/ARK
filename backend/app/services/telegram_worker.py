# app/services/telegram_worker.py
import os
import asyncio
import json
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
		payload = None
		try:
			payload = json.loads(message)
		except Exception:
			# если это просто строка
			payload = {"text": message}

		text = payload.get("text", "")
		msg_type = payload.get("type", "info")

		if msg_type == "ml_report":
			# уведомление о завершении ML обучения
			model_type = payload.get("model_type", "sklearn")
			metrics = payload.get("metrics", {})
			text = (
					f"🤖 ML обучение завершено ({model_type})\n"
					f"Accuracy: {metrics.get('accuracy', '-')}\n"
					f"Precision: {metrics.get('precision', '-')}\n"
					f"Recall: {metrics.get('recall', '-')}"
			)

		elif msg_type == "error":
			text = f"❌ Ошибка: {payload.get('error', 'Неизвестная ошибка')}"

		await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

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
