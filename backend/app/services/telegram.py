# app/services/telegram.py
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from sqlalchemy import select

from app.utils.logger import logger
from app.db.schemas import TradeORM, SignalORM, UserORM, RiskLog
from app.services.rabbitmq import RabbitMQBroker
from app.utils.metrics import calculate_metrics
from app.config import Settings
from app.db.session import get_session
from app.services.strategy_service import load_strategies
from app.services.risk import RiskService

settings = Settings()
bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()

class TelegramService:
	def __init__(self, bot: Bot, chat_id: str):
		self.bot = bot
		self.chat_id = chat_id

	async def send_message(self, text: str):
		logger.info(f"Отправка сообщения в Telegram: {text}")
		await self.bot.send_message(chat_id=self.chat_id, text=text)

	async def send_trade_notification(self, trade: dict, user_id: int | None = None):
		if user_id:
			async with get_session() as session:
					result = await session.execute(select(UserORM).filter(UserORM.id == user_id))
					user = result.scalars().first()
					if user and user.settings and not user.settings.get("notifications_enabled", True):
						logger.info(f"🔕 Уведомления отключены для пользователя {user.username}")
						return

		msg = (
			f"📊 Сделка по {trade.get('pair', 'N/A')}\n"
			f"Статус: {trade.get('status', '-')}\n"
			f"Вход: {trade.get('entry', '-')}\n"
			f"Выход: {trade.get('exit', '-')}\n"
			f"TP: {trade.get('take_profit', '-')}\n"
			f"SL: {trade.get('stop_loss', '-')}\n"
			f"Leverage: {trade.get('leverage', '-')}\n"
			f"Confidence: {trade.get('confidence_score', '-')}"
		)
		await self.send_message(msg)

	async def send_error(self, error: str, user_id: int | None = None,
								symbol: str = "-", position_size: float = 0.0, deposit: float = 0.0):
		if user_id:
			async with get_session() as session:
					result = await session.execute(select(UserORM).filter(UserORM.id == user_id))
					user = result.scalars().first()
					if user and user.settings and not user.settings.get("notifications_enabled", True):
						logger.info(f"🔕 Ошибки не отправляются — уведомления отключены для пользователя {user.username}")
						return

		msg = f"❌ Ошибка: {error}\nСимвол: {symbol}, Размер позиции: {position_size:.4f}, Депозит: {deposit:.2f}"
		await self.send_message(msg)

	async def send_order_cancelled(self, symbol: str, order_id: str, reason: str = "Cancelled"):
		msg = f"❌ Ордер отменён: {symbol}, id={order_id}, причина: {reason}"
		await self.send_message(msg)

	async def send_position_closed(self, symbol: str, amount: float, side: str, exit_price: float):
		msg = f"📉 Позиция закрыта: {symbol} {amount} {side} @ {exit_price}"
		await self.send_message(msg)


telegram_service = TelegramService(bot, settings.TELEGRAM_CHAT_ID)
broker = RabbitMQBroker()

def is_authorized(message: types.Message) -> bool:
	if str(message.chat.id) != settings.TELEGRAM_CHAT_ID:
		logger.warning(f"Попытка доступа от чужого chat_id: {message.chat.id}")
		return False
	return True

@dp.message(Command("start"))
async def start_command(message: types.Message):
	if not is_authorized(message):
		return
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и статистику.")

@dp.message(Command("status"))
async def status_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(TradeORM).where(TradeORM.status == "open"))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([
					f"{t.symbol} {t.side} {t.amount} @ {t.price} (Lev={t.leverage}, Conf={t.confidence_score})"
					for t in trades
			])
			await message.answer(f"📌 Активные позиции:\n{msg}")
		else:
			await message.answer("Пока нет открытых позиций.")

@dp.message(Command("trades"))
async def trades_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp.desc()).limit(10))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([
					f"{t.symbol} {t.side} {t.amount} @ {t.price} ({t.status}, Lev={t.leverage}, Conf={t.confidence_score})"
					for t in trades
			])
			await message.answer(f"📊 Последние сделки:\n{msg}")
		else:
			await message.answer("История сделок пуста.")

@dp.message(Command("report"))
async def report_command(message: types.Message):
	if not is_authorized(message):
		return
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
	async with get_session() as session:
		strategies = await load_strategies(session)
		await message.answer(f"⚙️ Текущие настройки стратегии:\n{strategies}")

@dp.message(Command("risk"))
async def risk_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		risk_service = RiskService(db_session=session)
		await risk_service.refresh_config()
		limits = await risk_service.get_limits(user_id=None)
		msg = (
			f"📉 Лимиты риск менеджмента:\n"
			f"Stop Loss (из стратегии): {limits.get('stop_loss_pct', '-')}\n"
			f"Default Trade Loss: {limits.get('default_trade_loss_pct', '-')}\n"
			f"Макс. количество сделок: {limits.get('max_trades', '-')}\n"
			f"Макс. плечо: {limits.get('max_leverage', '-')}\n"
			f"Макс. дневной убыток: {limits.get('max_daily_loss', '-')}\n"
			f"Risk/Reward Ratio: {limits.get('risk_reward_ratio', '-')}\n"
			f"Cooldown: {limits.get('cooldown_between_trades', '-')}\n"
			f"Dynamic Allocation: {limits.get('dynamic_allocation', False)}"
		)
		await message.answer(msg)

@dp.message(Command("violations"))
async def violations_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(
			select(RiskLog).order_by(RiskLog.timestamp.desc()).limit(5)
		)
		violations = result.scalars().all()
		if violations:
			msg = "\n".join([
					f"{v.timestamp} — {v.reason} (symbol={v.symbol}, pos={v.position_size}, dep={v.deposit})"
					for v in violations
			])
			await message.answer(f"⚠️ Последние нарушения риск менеджмента:\n{msg}")
		else:
			await message.answer("Нарушений риск менеджмента не зафиксировано.")

@dp.message(Command("metrics"))
async def metrics_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(TradeORM))
		trades = result.scalars().all()
		metrics = calculate_metrics(trades)
		msg = (
			f"📈 Метрики по сделкам:\n"
			f"Всего сделок: {metrics['trades_count']}\n"
			f"Winrate: {metrics['winrate']:.2%}\n"
			f"Средний профит: {metrics['average_profit']:.2f}\n"
			f"Суммарный профит: {metrics['total_profit']:.2f}\n"
			f"Макс. просадка: {metrics['max_drawdown']:.2f}"
		)
		await message.answer(msg)

@dp.message(Command("signal"))
async def signal_command(message: types.Message):
	if not is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(SignalORM).order_by(SignalORM.timestamp.desc()).limit(5))
		signals = result.scalars().all()
		if signals:
			msg = "\n".join([
					f"{s.timestamp} {s.symbol} {s.direction} "
					f"(strength={s.strength}, conf={s.confidence})"
					for s in signals
			])
			await message.answer(f"📡 Последние сигналы:\n{msg}")
		else:
			await message.answer("Сигналы отсутствуют.")

@dp.message(Command("id"))
async def id_command(message: types.Message):
	logger.info("Выполнена команда /id")
	await message.answer(f"Ваш chat_id: {message.chat.id}")

@dp.message(Command("help"))
async def help_command(message: types.Message):
	if not is_authorized(message):
		return
	msg = (
		"📖 Доступные команды:\n"
		"/start — запуск бота\n"
		"/status — активные позиции\n"
		"/trades — последние сделки\n"
		"/report — отчёт по стратегиям\n"
		"/config — настройки стратегий\n"
		"/risk — лимиты риск менеджмента\n"
		"/violations — нарушения риск менеджмента\n"
		"/metrics — метрики по сделкам\n"
		"/signal — последние сигналы\n"
		"/id — показать chat_id\n"
		"/help — список команд"
	)
	await message.answer(msg)

# --- Запуск бота ---
async def main():
	logger.info("Запуск Telegram-бота...")
	await broker.connect()
	await dp.start_polling(bot)

if __name__ == "__main__":
	asyncio.run(main())
