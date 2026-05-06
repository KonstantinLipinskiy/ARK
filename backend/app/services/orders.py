import ccxt.async_support as ccxt
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.utils.logger import logger
from app.services.risk import RiskService
from app.services.rabbitmq import RabbitMQBroker
from app.db.schemas import TradeORM
from app.services.ml import MLService
from app.services.strategy_service import load_strategies
from app.db.session import async_engine  # 🔹 engine для временной сессии

broker = RabbitMQBroker()
asyncio.create_task(broker.connect())

ml_service = MLService()
ml_service.load_model("models/sklearn_model.pkl", model_type="sklearn")

# --- INIT ---
def get_exchange():
	exchange_class = getattr(ccxt, settings.EXCHANGE_CONFIG["name"])
	exchange = exchange_class({
		"apiKey": settings.EXCHANGE_CONFIG["api_key"],
		"secret": settings.EXCHANGE_CONFIG["api_secret"],
		"enableRateLimit": True,
		"test": settings.EXCHANGE_CONFIG["mode"] == "testnet",
		"adjustForTimeDifference": True,
	})

	trading_mode = settings.TRADING_MODE
	if trading_mode == "futures":
		exchange.options["defaultType"] = "linear"
	else:
		exchange.options["defaultType"] = "spot"

	return exchange

# --- BALANCE ---
async def get_balance(currency: str = "USDT"):
	try:
		exchange = get_exchange()
		balance = await exchange.fetch_balance()
		return balance["free"].get(currency, 0.0)
	except Exception as e:
		logger.error(f"❌ Balance error: {e}")
		return 0.0

# --- ML FEATURES ---
def build_features(symbol: str, price: float) -> dict:
	"""Формируем признаки для ML модели (пример)."""
	return {
		"ema": 25.3,
		"rsi": 62.1,
		"macd": -0.004,
		"hour": datetime.utcnow().hour,
		"atr": 0.012,
	}

# --- ORDERS ---
async def create_order(
	symbol: str,
	side: str,
	amount: float = None,
	order_type: str = "market",
	price: float = None,
	stop_price: float = None,
	risk_service: RiskService = None,
):
	try:
		exchange = get_exchange()
		params = {}
		if stop_price:
			params["stopPrice"] = stop_price

		trading_mode = settings.TRADING_MODE
		if trading_mode == "futures":
			params.update({"reduceOnly": False, "marginType": "isolated"})

		features = build_features(symbol, price or 1.0)
		probability = ml_service.predict_signal(features)
		signal_strength = probability * 2

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=signal_strength
			)

			valid = await risk_service.validate_trade(
					symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					open_trades=1,
					total_loss_pct=total_loss_pct,
					strength=signal_strength
			)
			if not valid:
					return {"error": "Risk validation failed"}

			amount = position_size

		order = await exchange.create_order(
			symbol=symbol,
			type=order_type,
			side=side,
			amount=amount,
			price=price,
			params=params
		)

		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=price or 0.0,
			status="open"
		)
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		await broker.publish_telegram({"text": f"✅ Order created: {symbol} {side} {amount} {order_type}"})
		return order
	except Exception as e:
		logger.error(f"❌ Order error: {e}")
		await broker.publish_telegram({"text": f"❌ Order failed: {e}"})
		return {"error": str(e)}

# --- STOP ORDER ---
async def create_stop_order(
	symbol: str,
	side: str,
	amount: float = None,
	stop_price: float = None,
	order_type: str = "stop_market",
	risk_service: RiskService = None,
):
	try:
		exchange = get_exchange()
		params = {"stopPrice": stop_price}

		features = build_features(symbol, stop_price or 1.0)
		probability = ml_service.predict_signal(features)
		signal_strength = probability * 2

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=stop_price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=signal_strength
			)
			valid = await risk_service.validate_trade(
					symbol, deposit=deposit, entry_price=stop_price or 1.0,
					stop_loss_pct=stop_loss_pct, open_trades=1,
					total_loss_pct=total_loss_pct, strength=signal_strength
			)
			if not valid:
					return {"error": "Risk validation failed"}
			amount = position_size

		order = await exchange.create_order(symbol, order_type, side, amount, None, params)

		trade = TradeORM(symbol=symbol, side=side, amount=amount, price=stop_price or 0.0, status="open")
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		await broker.publish_telegram({"text": f"📌 Stop order created: {symbol} {side} {amount} @ {stop_price}"})
		return order
	except Exception as e:
		logger.error(f"❌ Stop order error: {e}")
		await broker.publish_telegram({"text": f"❌ Stop order failed: {e}"})
		return {"error": str(e)}

# --- OCO ORDER ---
async def create_oco_order(
	symbol: str,
	side: str,
	amount: float = None,
	price: float = None,
	stop_price: float = None,
	risk_service: RiskService = None,
):
	try:
		exchange = get_exchange()
		params = {"type": "oco", "price": price, "stopPrice": stop_price}

		features = build_features(symbol, price or 1.0)
		probability = ml_service.predict_signal(features)
		signal_strength = probability * 2

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			position_size = await risk_service.calculate_position_size(
					symbol=symbol, deposit=deposit, entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct, strength=signal_strength
			)
			valid = await risk_service.validate_trade(
					symbol, deposit=deposit, entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct, open_trades=1,
					total_loss_pct=total_loss_pct, strength=signal_strength
			)
			if not valid:
					return {"error": "Risk validation failed"}
			amount = position_size

		order = await exchange.create_order(symbol, "limit", side, amount, price, params)

		trade = TradeORM(symbol=symbol, side=side, amount=amount, price=price or 0.0, status="open")
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

		await broker.publish_telegram({"text": f"🔀 OCO order created: {symbol} {side} {amount} TP={price}, SL={stop_price}"})
		return order
	except Exception as e:
		logger.error(f"❌ OCO order error: {e}")
		await broker.publish_telegram({"text": f"❌ OCO order failed: {e}"})
		return {"error": str(e)}

# --- FUTURES ORDER ---
async def create_futures_order(
	symbol: str,
	side: str,
	amount: float = None,
	leverage: int = None,
	order_type: str = "market",
	price: float = None,
	reduce_only: bool = False,
	margin_type: str = "isolated",
	risk_service: RiskService = None,
):
	try:
		exchange = get_exchange()

		features = build_features(symbol, price or 1.0)
		probability = ml_service.predict_signal(features)
		signal_strength = probability * 2

		if risk_service:
			await risk_service.refresh_config()

			# 🔹 Берём плечо из RiskService
			leverage = risk_service.calculate_leverage(symbol, signal_strength)

			deposit = await get_balance("USDT")

			# 🔹 Берём stop_loss из стратегии
			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)

			# 🔹 Берём лимит убытка из risk_settings
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=signal_strength
			)

			valid = await risk_service.validate_trade(
					symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					open_trades=1,
					total_loss_pct=total_loss_pct,
					strength=signal_strength
			)
			if not valid:
					return {"error": "Risk validation failed"}

			amount = position_size
		else:
			# 🔹 создаём временную сессию для загрузки стратегий
			async with AsyncSession(async_engine) as session:
					strategies = await load_strategies(session)
					leverage = strategies[symbol].get("leverage", 1)

		await exchange.set_leverage(leverage, symbol)
		params = {"reduceOnly": reduce_only, "marginType": margin_type}

		order = await exchange.create_order(symbol, order_type, side, amount, price, params)

		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=price or 0.0,
			status="open"
		)
		if risk_service:
			risk_service.db_session.add(trade)
			await risk_service.db_session.commit()

		await broker.publish_telegram({"text": f"⚡ Futures order created: {symbol} {side} {amount} x{leverage}"})
		return order
	except Exception as e:
		logger.error(f"❌ Futures order error: {e}")
		await broker.publish_telegram({"text": f"❌ Futures order failed: {e}"})
		return {"error": str(e)}
