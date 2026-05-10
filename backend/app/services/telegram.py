# app/services/telegram.py
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
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
	def __init__(self, bot: Bot):
		self.bot = bot

	async def send_message_to_user(self, user: UserORM, text: str):
		"""Отправка сообщения конкретному пользователю по его telegram_id."""
		if not user.telegram_id:
			logger.warning(f"❌ У пользователя {user.username} нет telegram_id")
			return
		if user.settings and not user.settings.get("notifications_enabled", True):
			logger.info(f"🔕 Уведомления отключены для пользователя {user.username}")
			return
		await self.bot.send_message(chat_id=user.telegram_id, text=text)

	async def send_message_by_id(self, telegram_id: str, text: str):
		"""Отправка сообщения по telegram_id напрямую."""
		await self.bot.send_message(chat_id=telegram_id, text=text)

	async def send_trade_notification(self, trade: dict, user_id: int | None = None):
		"""Уведомление о сделке с расширенным форматом (PnL, SL, TP)."""
		async with get_session() as session:
			if user_id:
					result = await session.execute(select(UserORM).filter(UserORM.id == user_id))
					user = result.scalars().first()
					if user:
						msg = (
							f"💹 Сделка: {trade.get('symbol', 'N/A')} {trade.get('side', '-')}\n"
							f"Статус: {trade.get('status', '-')}\n"
							f"Вход: {trade.get('entry_price', '-')}\n"
							f"Выход: {trade.get('exit_price', '-')}\n"
							f"PnL: {trade.get('profit_loss', '-')}\n"
							f"Стоп-лосс: {trade.get('stop_loss', '-')}\n"
							f"Тейк-профит: {trade.get('take_profit', '-')}\n"
							f"Leverage: {trade.get('leverage', '-')}\n"
							f"Confidence: {trade.get('confidence_score', '-')}\n"
							f"Риск: {trade.get('risk_reason', '-')}"
						)
						await self.send_message_to_user(user, msg)
						logger.info(f"📤 Уведомление о сделке отправлено пользователю {user.username}")

	async def send_signal_notification(self, signal: dict, user_id: int | None = None):
		"""Уведомление о новом сигнале."""
		async with get_session() as session:
			if user_id:
					result = await session.execute(select(UserORM).filter(UserORM.id == user_id))
					user = result.scalars().first()
					if user:
						msg = (
							f"📈 Новый сигнал: {signal.get('symbol', 'N/A')} {signal.get('direction', '-')}\n"
							f"Индикатор: {signal.get('indicator', '-')}\n"
							f"Сила: {signal.get('strength', '-')}\n"
							f"Confidence: {signal.get('confidence', '-')}\n"
							f"Источник: {signal.get('source', '-')}\n"
							f"Время: {signal.get('timestamp', '-')}"
						)
						await self.send_message_to_user(user, msg)
						logger.info(f"📤 Уведомление о сигнале отправлено пользователю {user.username}")

	async def send_error(self, error: str, user_id: int | None = None,
								symbol: str = "-", position_size: float = 0.0, deposit: float = 0.0):
		async with get_session() as session:
			if user_id:
					result = await session.execute(select(UserORM).filter(UserORM.id == user_id))
					user = result.scalars().first()
					if user:
						msg = (
							f"❌ Ошибка: {error}\n"
							f"Символ: {symbol}\n"
							f"Размер позиции: {position_size:.4f}\n"
							f"Депозит: {deposit:.2f}"
						)
						await self.send_message_to_user(user, msg)

	async def send_order_cancelled(self, user: UserORM, symbol: str, order_id: str, reason: str = "Cancelled"):
		msg = f"❌ Ордер отменён: {symbol}, id={order_id}, причина: {reason}"
		await self.send_message_to_user(user, msg)

	async def send_position_closed(self, user: UserORM, symbol: str, amount: float, side: str, exit_price: float,
											stop_loss: float | None = None, risk: float | None = None):
		msg = (
			f"📉 Позиция закрыта: {symbol} {amount} {side} @ {exit_price}\n"
			f"Стоп-лосс: {stop_loss if stop_loss else '-'}\n"
			f"Риск: {risk if risk else '-'}"
		)
		await self.send_message_to_user(user, msg)

	async def send_margin_mode_changed(self, user: UserORM, symbol: str, mode: str):
		msg = f"⚙️ Маржинальный режим изменён: {symbol}, новый режим = {mode}"
		await self.send_message_to_user(user, msg)

	# 🔹 Новые уведомления для админских функций
	async def send_user_blocked(self, user: UserORM):
		msg = f"⛔ Пользователь {user.username} (ID={user.id}) был заблокирован администратором."
		await self.send_message_to_user(user, msg)
		logger.info(f"📤 Уведомление о блокировке отправлено пользователю {user.username}")

	async def send_strategy_updated(self, strategy: dict):
		msg = (
			f"⚙️ Стратегия обновлена: {strategy.get('symbol', '-')}\n"
			f"Параметры: {strategy}"
		)
		# Здесь можно рассылать уведомление всем админам или конкретным пользователям
		logger.info(f"📤 Уведомление об изменении стратегии: {strategy.get('symbol', '-')}")


telegram_service = TelegramService(bot)
broker = RabbitMQBroker()

async def get_user_by_chat_id(chat_id: int) -> UserORM | None:
	async with get_session() as session:
		result = await session.execute(select(UserORM).filter(UserORM.telegram_id == str(chat_id)))
		return result.scalars().first()

async def is_authorized(message: types.Message) -> bool:
	user = await get_user_by_chat_id(message.chat.id)
	if not user or user.status != "active":
		logger.warning(f"Попытка доступа от неавторизованного chat_id: {message.chat.id}")
		return False
	return True

async def is_admin(message: types.Message) -> bool:
	user = await get_user_by_chat_id(message.chat.id)
	return bool(user and user.is_admin)

@dp.message(Command("start"))
async def start_command(message: types.Message):
	if not await is_authorized(message):
		return
	await message.answer("Привет! Я ARK Bot. Буду присылать уведомления о сделках и сигналах.")

@dp.message(Command("status"))
async def status_command(message: types.Message):
	if not await is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(TradeORM).where(TradeORM.status == "open"))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([
					f"{t.symbol} {t.side} {t.amount} @ {t.price} (Lev={t.leverage}, Conf={t.confidence_score}, SL={t.stop_loss}, Risk={t.risk})"
					for t in trades
			])
			await message.answer(f"📌 Активные позиции:\n{msg}")
		else:
			await message.answer("Пока нет открытых позиций.")

@dp.message(Command("trades"))
async def trades_command(message: types.Message):
	if not await is_authorized(message):
		return
	async with get_session() as session:
		result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp.desc()).limit(10))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([
					f"{t.symbol} {t.side} {t.amount} @ {t.price} ({t.status}, Lev={t.leverage}, Conf={t.confidence_score}, SL={t.stop_loss}, Risk={t.risk})"
					for t in trades
			])
			await message.answer(f"📊 Последние сделки:\n{msg}")
		else:
			await message.answer("История сделок пуста.")

@dp.message(Command("report"))
async def report_command(message: types.Message):
	if not await is_authorized(message):
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
	if not await is_authorized(message):
		return
	if not await is_admin(message):
		await message.answer("⛔ Эта команда доступна только администраторам.")
		return
	async with get_session() as session:
		strategies = await load_strategies(session)
		await message.answer(f"⚙️ Текущие настройки стратегии:\n{strategies}")

@dp.message(Command("risk"))
async def risk_command(message: types.Message):
	if not await is_authorized(message):
		return
	if not await is_admin(message):
		await message.answer("⛔ Эта команда доступна только администраторам.")
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
			f"Dynamic Allocation: {limits.get('dynamic_allocation', False)}\n"
			f"Strength Multiplier: {limits.get('strength_multiplier', '-')}"
		)
		await message.answer(msg)
