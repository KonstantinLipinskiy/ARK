#app/services/telegram_worker.py
import os
import asyncio
from aiogram import Bot
from sqlalchemy import select

from app.utils.logger import logger
from app.broker.rabbitmq import RabbitMQBroker
from app.db.session import get_session
from app.db.schemas import UserORM
from app.services.reports import ReportsService
from app.config import settings

bot = Bot(token=settings.TELEGRAM_TOKEN)
broker = RabbitMQBroker()
reports_service = ReportsService()

async def get_user_by_id(user_id: int) -> UserORM | None:
	"""Получить пользователя по его ID из БД."""
	async with get_session() as session:
		result = await session.execute(
			select(UserORM).where(UserORM.id == user_id)
		)
		return result.scalars().first()

async def process_notification(payload: dict):
	"""
	Обработка уведомления из очереди RabbitMQ.
	payload: dict (RabbitMQ уже возвращает JSON-декодированный объект)
	"""
	logger.info(f"📨 Telegram worker получил сообщение: {payload}")
	try:
		text = payload.get("text", "")
		msg_type = payload.get("type", "info")
		user_id = payload.get("user_id")

		# --- Форматирование разных типов уведомлений ---
		if msg_type == "ml_report":
			model_type = payload.get("model_type", "sklearn")
			metrics = payload.get("metrics", {})
			text = (
				f"🤖 ML обучение завершено ({model_type})\n"
				f"Accuracy: {metrics.get('accuracy', '-')}\n"
				f"Precision: {metrics.get('precision', '-')}\n"
				f"Recall: {metrics.get('recall', '-')}"
			)

		elif msg_type == "ml_predict":
			predictions = payload.get("predictions", [])
			text = (
				f"🔮 ML прогноз ({payload.get('model_type', 'sklearn')})\n"
				f"Результаты: {predictions}"
			)

		elif msg_type == "error":
			text = f"❌ Ошибка: {payload.get('error', 'Неизвестная ошибка')}"

		elif msg_type == "trade":
			trade = payload.get("trade", {})
			text = (
				f"📊 Сделка по {trade.get('pair', 'N/A')}\n"
				f"Статус: {trade.get('status', '-')}\n"
				f"Вход: {trade.get('entry', '-')}\n"
				f"Выход: {trade.get('exit', '-')}\n"
				f"TP: {trade.get('take_profit', '-')}\n"
				f"SL: {trade.get('stop_loss', '-')}\n"
				f"Leverage: {trade.get('leverage', '-')}\n"
				f"Confidence: {trade.get('confidence_score', '-')}"
			)

		elif msg_type == "risk_violation":
			text = (
				f"⚠️ Нарушение риск-менеджмента:\n"
				f"Причина: {payload.get('reason', '-')}\n"
				f"Символ: {payload.get('symbol', '-')}\n"
				f"Размер позиции: {payload.get('position_size', '-')}\n"
				f"Депозит: {payload.get('deposit', '-')}"
			)

		elif msg_type == "report":
			report_name = payload.get("report_name", "Отчёт")
			trades = payload.get("trades", [])
			# 🔹 Используем ReportsService для форматированного отчёта
			summary = reports_service.generate_rag_report(trades, output_format="markdown")
			text = (
				f"📑 Новый отчёт: {report_name}\n"
				f"{summary}"
			)

		elif msg_type == "alert":
			reason = payload.get("reason", "Неизвестная причина")
			text = (
				f"🚨 ALERT!\n"
				f"Тип: {payload.get('alert_type', '-')}\n"
				f"Причина: {reason}\n"
				f"Детали: {payload.get('details', '-')}"
			)

		elif msg_type == "log":
			text = (
				f"📝 Лог:\n"
				f"{payload.get('details', '-')}"
			)

		# --- Отправка пользователю ---
		if user_id:
			user = await get_user_by_id(user_id)
			if user and user.telegram_id:
				if user.settings and not user.settings.get("notifications_enabled", True):
					logger.info(f"🔕 Уведомления отключены для пользователя {user.username}")
					return
				try:
					await bot.send_message(chat_id=user.telegram_id, text=text)
					logger.info(f"📤 Уведомление отправлено пользователю {user.username} ({user.telegram_id})")
				except Exception as e:
					logger.error(f"❌ Ошибка отправки сообщения пользователю {user.username}: {e}")
			else:
				logger.warning(f"❌ Пользователь {user_id} не найден или нет telegram_id")
		else:
			# fallback: если user_id не указан, можно отправить в общий чат (например, админский)
			default_chat_id = os.getenv("TELEGRAM_CHAT_ID")
			if default_chat_id:
				try:
					await bot.send_message(chat_id=default_chat_id, text=text)
					logger.info(f"📤 Уведомление отправлено в общий чат {default_chat_id}")
				except Exception as e:
					logger.error(f"❌ Ошибка отправки сообщения в общий чат {default_chat_id}: {e}")

	except Exception as e:
		logger.error(f"❌ Ошибка обработки уведомления: {e}")
		# публикуем ошибку в alerts_queue
		await broker.publish_alert({"type": "telegram_error", "error": str(e), "payload": payload})

async def consume_notifications():
	"""Подключение к RabbitMQ и прослушивание очередей уведомлений."""
	await broker.connect()
	# слушаем telegram_notifications
	await broker.consume_telegram(process_notification)
	# слушаем alerts и logs
	await broker.consume_alerts(process_notification)
	await broker.consume_logs(process_notification)

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
