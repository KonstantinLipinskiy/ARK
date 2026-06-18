# app/services/orders.py
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.logger import logger
from app.services.risk_service import calculate_position_size, validate_trade
from app.broker.rabbitmq import RabbitMQBroker
from app.db.schemas import TradeORM
from app.services.ml import MLService
from app.services.exchange import get_ohlcv, get_exchange 

# --- ML Service ---
ml_service = MLService()
ml_service.load_model(settings.MODEL_PATH, model_type=settings.MODEL_TYPE)

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
async def build_features(symbol: str, price: float, db_session: AsyncSession) -> dict:
	"""
	Формируем признаки для ML модели на основе реальных свечей.
	"""
	df = await get_ohlcv(db_session, symbol=symbol, timeframe="1h", limit=100, as_dataframe=True)
	prepared = ml_service.prepare_data(df.to_dict(orient="records"))
	features = prepared.iloc[-1].fillna(0).to_dict()
	return features

# --- Общий обработчик ошибок ---
async def handle_order_error(context: str, error: Exception, broker: RabbitMQBroker):
	logger.error(f"❌ {context} error: {error}")
	await broker.publish_telegram({
		"type": "error",
		"error": f"{context} failed: {error}"
	})
	return {"error": str(error)}

# --- ORDERS ---
async def create_order(symbol: str, side: str, amount: float = None,
						order_type: str = "market", price: float = None,
						stop_price: float = None, db_session: AsyncSession = None,
						broker: RabbitMQBroker = None):
	try:
		exchange = get_exchange()
		params = {}
		if stop_price:
			params["stopPrice"] = stop_price

		if settings.TRADING_MODE == "futures":
			params.update({"reduceOnly": False, "marginType": "isolated"})

		# --- ML прогноз ---
		features = await build_features(symbol, price or 1.0, db_session)
		prediction = ml_service.predict_with_confidence(features)
		probability = prediction["success_probability"]
		confidence_score = prediction["confidence_score"]
		signal_strength = probability * settings.SIGNAL_MULTIPLIER

		# --- Фильтрация слабых сигналов ---
		if confidence_score < settings.CONFIDENCE_THRESHOLD:
			await broker.publish_telegram({
				"type": "signal_rejected",
				"trade": {"pair": symbol, "side": side},
				"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

		deposit = await get_balance("USDT")
		stop_loss_pct = 0.02  # берём из стратегии, можно расширить
		total_loss_pct = 0.01

		position_size = await calculate_position_size(
			symbol=symbol,
			deposit=deposit,
			entry_price=price or 1.0,
			stop_loss_pct=stop_loss_pct,
			strength=signal_strength,
			ml_confidence=confidence_score
		)
		amount = position_size

		valid = await validate_trade(
			symbol,
			deposit=deposit,
			entry_price=price or 1.0,
			stop_loss_pct=stop_loss_pct,
			open_trades=1,
			total_loss_pct=total_loss_pct,
			strength=signal_strength
		)
		if not valid:
			await broker.publish_telegram({
				"type": "risk_violation",
				"trade": {"pair": symbol, "side": side},
				"reason": "Risk validation failed"
			})
			return {"error": "Risk validation failed"}

		order = await exchange.create_order(symbol, order_type, side, amount, price, params)

		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=price or 0.0,
			entry_price=price or 0.0,
			stop_loss=stop_price,
			leverage=settings.DEFAULT_DEPOSIT,
			confidence_score=confidence_score,
			status="open"
		)
		db_session.add(trade)
		await db_session.commit()

		await broker.publish_telegram({
			"type": "trade",
			"trade": {
				"pair": symbol,
				"side": side,
				"amount": amount,
				"entry": price,
				"stop_loss": stop_price,
				"leverage": trade.leverage,
				"confidence_score": confidence_score
			}
		})
		return order
	except Exception as e:
		return await handle_order_error("Order", e, broker)

# --- STOP ORDER ---
async def create_stop_order(symbol: str, side: str, amount: float = None,
							stop_price: float = None, order_type: str = "stop_market",
							db_session: AsyncSession = None, broker: RabbitMQBroker = None):
	try:
		exchange = get_exchange()
		params = {"stopPrice": stop_price}

		features = await build_features(symbol, stop_price or 1.0, db_session)
		prediction = ml_service.predict_with_confidence(features)
		confidence_score = prediction["confidence_score"]
		signal_strength = prediction["success_probability"] * settings.SIGNAL_MULTIPLIER

		if confidence_score < settings.CONFIDENCE_THRESHOLD:
			await broker.publish_telegram({
				"type": "signal_rejected",
				"trade": {"pair": symbol, "side": side},
				"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

		deposit = await get_balance("USDT")
		stop_loss_pct = 0.02
		total_loss_pct = 0.01

		position_size = await calculate_position_size(
			symbol=symbol,
			deposit=deposit,
			entry_price=stop_price or 1.0,
			stop_loss_pct=stop_loss_pct,
			strength=signal_strength,
			ml_confidence=confidence_score
		)
		amount = position_size

		valid = await validate_trade(
			symbol, deposit=deposit, entry_price=stop_price or 1.0,
			stop_loss_pct=stop_loss_pct, open_trades=1,
			total_loss_pct=total_loss_pct, strength=signal_strength
		)
		if not valid:
			await broker.publish_telegram({
				"type": "risk_violation",
				"trade": {"pair": symbol, "side": side},
				"reason": "Risk validation failed"
			})
			return {"error": "Risk validation failed"}

		order = await exchange.create_order(symbol, order_type, side, amount, None, params)

		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=stop_price or 0.0,
			stop_loss=stop_price,
			confidence_score=confidence_score,
			status="open"
		)
		db_session.add(trade)
		await db_session.commit()

		await broker.publish_telegram({
			"type": "trade",
			"trade": {
				"pair": symbol,
				"side": side,
				"amount": amount,
				"stop_loss": stop_price,
				"confidence_score": confidence_score
			}
		})
		return order
	except Exception as e:
		return await handle_order_error("Stop order", e, broker)

# --- OCO ORDER ---
async def create_oco_order(symbol: str, side: str, amount: float = None,
							price: float = None, stop_price: float = None,
							db_session: AsyncSession = None, broker: RabbitMQBroker = None):
	try:
		exchange = get_exchange()
		params = {"type": "oco", "price": price, "stopPrice": stop_price}  # TODO: проверить совместимость с конкретной биржей

		features = await build_features(symbol, price or 1.0, db_session)
		prediction = ml_service.predict_with_confidence(features)
		confidence_score = prediction["confidence_score"]
		signal_strength = prediction["success_probability"] * settings.SIGNAL_MULTIPLIER

		if confidence_score < settings.CONFIDENCE_THRESHOLD:
			await broker.publish_telegram({
				"type": "signal_rejected",
				"trade": {"pair": symbol, "side": side},
				"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

		deposit = await get_balance("USDT")
		stop_loss_pct = 0.02
		total_loss_pct = 0.01

		position_size = await calculate_position_size(
			symbol=symbol,
			deposit=deposit,
			entry_price=price or 1.0,
			stop_loss_pct=stop_loss_pct,
			strength=signal_strength,
			ml_confidence=confidence_score
		)
		amount = position_size

		valid = await validate_trade(
			symbol,
			deposit=deposit,
			entry_price=price or 1.0,
			stop_loss_pct=stop_loss_pct,
			open_trades=1,
			total_loss_pct=total_loss_pct,
			strength=signal_strength
		)
		if not valid:
			await broker.publish_telegram({
				"type": "risk_violation",
				"trade": {"pair": symbol, "side": side},
				"reason": "Risk validation failed"
			})
			return {"error": "Risk validation failed"}

		order = await exchange.create_order(symbol, "limit", side, amount, price, params)

		trade = TradeORM(
			symbol=symbol,
			side=side,
			amount=amount,
			price=price or 0.0,
			entry_price=price or 0.0,
			stop_loss=stop_price,
			take_profit=price,
			confidence_score=confidence_score,
			status="open"
		)
		db_session.add(trade)
		await db_session.commit()

		await broker.publish_telegram({
			"type": "trade",
			"trade": {
				"pair": symbol,
				"side": side,
				"amount": amount,
				"entry": price,
				"stop_loss": stop_price,
				"take_profit": price,
				"confidence_score": confidence_score
			}
		})
		return order
	except Exception as e:
		return await handle_order_error("OCO order", e, broker)
