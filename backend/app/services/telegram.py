# app/services/telegram.py
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from sqlalchemy import select

from app.utils.logger import logger
from app.db.schemas import TradeORM, UserORM, UserStatus
from app.broker.rabbitmq import RabbitMQBroker
from app.utils.metrics import calculate_metrics
from app.config import Settings
from app.db.session import get_session
from app.services.exchange import load_strategies
from app.services.risk import RiskService
from app.services.reports import ReportsService

settings = Settings()
bot = Bot(token=settings.TELEGRAM_TOKEN)
dp = Dispatcher()
broker = RabbitMQBroker()

class TelegramService:
	def __init__(self, bot: Bot):
		self.bot = bot
		self.reports_service = ReportsService()

	async def send_message(self, text: str, telegram_id: str | None = None):
		"""Универсальная отправка сообщения (по умолчанию админу) через брокер."""
		target_id = telegram_id or getattr(settings, "ADMIN_TELEGRAM_ID", None)
		if not target_id:
			logger.error("❌ ADMIN_TELEGRAM_ID не задан",
							extra={"operation": "telegram_service", "collection": "config"})
			return
		payload = {"type": "info", "text": text, "user_id": None}
		await broker.publish_telegram(payload)
		logger.info(f"📤 Сообщение отправлено в очередь Telegram: {text}",
					extra={"operation": "telegram_service", "collection": "send"})

	async def send_message_to_user(self, user: UserORM, text: str):
		"""Отправка сообщения конкретному пользователю через брокер."""
		if not user.telegram_id:
			logger.warning(f"❌ У пользователя {user.username} нет telegram_id",
							extra={"operation": "telegram_service", "collection": "send"})
			return
		if user.settings and not user.settings.get("notifications_enabled", True):
			logger.info(f"🔕 Уведомления отключены для пользователя {user.username}",
						extra={"operation": "telegram_service", "collection": "send"})
			return
		payload = {"type": "info", "text": text, "user_id": user.id}
		await broker.publish_telegram(payload)
		logger.info(f"📤 Сообщение отправлено в очередь Telegram для {user.username}",
					extra={"operation": "telegram_service", "collection": "send"})

	async def send_message_by_id(self, telegram_id: str, text: str):
		"""Отправка сообщения по telegram_id напрямую через брокер."""
		if not telegram_id:
			logger.error("❌ ADMIN_TELEGRAM_ID не задан, невозможно отправить сообщение",
							extra={"operation": "telegram_service", "collection": "config"})
			return
		payload = {"type": "info", "text": text, "user_id": None}
		await broker.publish_telegram(payload)

	async def send_trade_notification(self, trade: dict, user_id: int | None = None):
		"""Уведомление о сделке."""
		payload = {"type": "trade", "trade": trade, "user_id": user_id}
		await broker.publish_telegram(payload)

	async def send_signal_notification(self, signal: dict, user_id: int | None = None):
		"""Уведомление о сигнале."""
		payload = {"type": "signal", "signal": signal, "user_id": user_id}
		await broker.publish_telegram(payload)

	async def send_error(self, error: str, user_id: int | None = None,
							symbol: str = "-", position_size: float = 0.0, deposit: float = 0.0):
		"""Уведомление об ошибке."""
		payload = {
			"type": "error",
			"error": error,
			"symbol": symbol,
			"position_size": position_size,
			"deposit": deposit,
			"user_id": user_id
		}
		await broker.publish_telegram(payload)

	async def send_order_cancelled(self, user: UserORM, symbol: str, order_id: str, reason: str = "Cancelled"):
		payload = {"type": "order_cancelled", "symbol": symbol, "order_id": order_id, "reason": reason, "user_id": user.id}
		await broker.publish_telegram(payload)

	async def send_position_closed(self, user: UserORM, symbol: str, amount: float, side: str, exit_price: float,
									stop_loss: float | None = None, risk: float | None = None):
		payload = {
			"type": "position_closed",
			"symbol": symbol,
			"amount": amount,
			"side": side,
			"exit_price": exit_price,
			"stop_loss": stop_loss,
			"risk": risk,
			"user_id": user.id
		}
		await broker.publish_telegram(payload)

	async def send_margin_mode_changed(self, user: UserORM, symbol: str, mode: str):
		payload = {"type": "margin_mode_changed", "symbol": symbol, "mode": mode, "user_id": user.id}
		await broker.publish_telegram(payload)

	async def send_user_blocked(self, user: UserORM):
		payload = {"type": "user_blocked", "user_id": user.id, "username": user.username}
		await broker.publish_telegram(payload)

	async def send_strategy_updated(self, strategy: dict, admin_id: str | None = None):
		payload = {"type": "strategy_updated", "strategy": strategy, "user_id": None}
		await broker.publish_telegram(payload)

telegram_service = TelegramService(bot)

# -------------------------------------------------------------------
# Вспомогательные функции авторизации
# -------------------------------------------------------------------
async def get_user_by_chat_id(chat_id: int) -> UserORM | None:
	async with get_session() as session:
		result = await session.execute(select(UserORM).where(UserORM.telegram_id == str(chat_id)))
		return result.scalars().first()

async def is_authorized(message: types.Message) -> bool:
	user = await get_user_by_chat_id(message.chat.id)
	if not user or user.status != UserStatus.active:
		logger.warning(f"Попытка доступа от неавторизованного chat_id: {message.chat.id}",
						extra={"operation": "telegram_service", "collection": "auth"})
		return False
	return True

async def is_admin(message: types.Message) -> bool:
	user = await get_user_by_chat_id(message.chat.id)
	return bool(user and user.is_admin)

# -------------------------------------------------------------------
# Команды Telegram-бота
# -------------------------------------------------------------------
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
		result = await session.execute(select(TradeORM).order_by(TradeORM.timestamp.desc()).limit(10))
		trades = result.scalars().all()
		if trades:
			msg = "\n".join([
				f"{t.symbol} {t.side} {t.amount} @ {t.price} "
				f"({t.status}, Lev={t.leverage}, Conf={t.confidence_score}, SL={t.stop_loss}, Risk={t.risk_reason})"
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
		report_text = telegram_service.reports_service.generate_report(
			[t.__dict__ for t in trades], output_format="markdown"
		)
		await message.answer(report_text)

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

@dp.message(Command("help"))
async def help_command(message: types.Message):
	"""
	Команда /help: выводит список всех доступных команд Telegram‑бота.
	"""
	if not await is_authorized(message):
		return
	help_text = (
		"📖 Список доступных команд:\n\n"
		"/start – приветственное сообщение и активация бота\n"
		"/status – показать активные позиции\n"
		"/trades – последние сделки\n"
		"/report – сформировать RAG‑отчёт по сделкам (markdown)\n"
		"/config – текущие настройки стратегии (только админ)\n"
		"/risk – лимиты риск‑менеджмента (только админ)\n"
		"/help – список команд и описание"
	)
	await message.answer(help_text)
