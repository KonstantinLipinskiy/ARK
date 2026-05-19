# app/services/orders.py
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
from app.services.exchange import load_strategies
from app.db.session import async_engine
from app.services.exchange import get_ohlcv


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
async def build_features(symbol: str, price: float, db_session: AsyncSession) -> dict:
	"""
	Формируем признаки для ML модели на основе реальных свечей.
	"""
	# Берём последние 100 часовых свечей
	df = await get_ohlcv(db_session, symbol=symbol, timeframe="1h", limit=100, as_dataframe=True)

	# Готовим признаки через MLService
	prepared = ml_service.prepare_data(df.to_dict(orient="records"))

	# Берём последнюю строку как актуальные признаки
	features = prepared.iloc[-1].fillna(0).to_dict()
	return features


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

		# --- ML прогноз ---
		features = await build_features(symbol, price or 1.0, risk_service.db_session)
		prediction = ml_service.predict_with_confidence(features)
		probability = prediction["success_probability"]
		confidence_score = prediction["confidence_score"]
		signal_strength = probability * 2

		# --- Фильтрация слабых сигналов ---
		CONFIDENCE_THRESHOLD = 0.2
		if confidence_score < CONFIDENCE_THRESHOLD:
			logger.info(f"⚠️ Сигнал отклонён: низкий confidence={confidence_score:.2f}")
			await broker.publish_telegram({
					"type": "signal_rejected",
					"trade": {"pair": symbol, "side": side},
					"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			# --- Адаптивная аллокация ---
			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=signal_strength,
					ml_confidence=confidence_score
			)
			amount = position_size * (0.5 + confidence_score)

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
					trade = TradeORM(
						symbol=symbol,
						side=side,
						amount=0.0,
						price=price or 0.0,
						status="cancelled",
						risk_reason="Risk validation failed"
					)
					risk_service.db_session.add(trade)
					await risk_service.db_session.commit()
					await broker.publish_telegram({
						"type": "risk_violation",
						"trade": {"pair": symbol, "side": side},
						"reason": "Risk validation failed"
					})
					return {"error": "Risk validation failed"}

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
			entry_price=price or 0.0,
			stop_loss=stop_price,
			leverage=risk_service.RISK_CONFIG.get("max_leverage", 1),
			confidence_score=confidence_score,
			status="open"
		)
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

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
		logger.error(f"❌ Order error: {e}")
		await broker.publish_telegram({"type": "error", "error": f"Order failed: {e}"})
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

		features = await build_features(symbol, stop_price or 1.0, risk_service.db_session)
		prediction = ml_service.predict_with_confidence(features)
		confidence_score = prediction["confidence_score"]
		signal_strength = prediction["success_probability"] * 2

		CONFIDENCE_THRESHOLD = 0.2
		if confidence_score < CONFIDENCE_THRESHOLD:
			await broker.publish_telegram({
					"type": "signal_rejected",
					"trade": {"pair": symbol, "side": side},
					"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

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
					strength=signal_strength,
					ml_confidence=confidence_score
			)
			amount = position_size * (0.5 + confidence_score)

			valid = await risk_service.validate_trade(
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
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

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
		logger.error(f"❌ Stop order error: {e}")
		await broker.publish_telegram({
			"type": "error",
			"error": f"Stop order failed: {e}"
		})
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

		# --- ML прогноз ---
		features = await build_features(symbol, price or 1.0, risk_service.db_session)
		prediction = ml_service.predict_with_confidence(features)
		confidence_score = prediction["confidence_score"]
		signal_strength = prediction["success_probability"] * 2

		# --- Фильтрация слабых сигналов ---
		CONFIDENCE_THRESHOLD = 0.2
		if confidence_score < CONFIDENCE_THRESHOLD:
			await broker.publish_telegram({
					"type": "signal_rejected",
					"trade": {"pair": symbol, "side": side},
					"confidence_score": confidence_score
			})
			return {"error": "Signal confidence too low"}

		if risk_service:
			await risk_service.refresh_config()
			deposit = await get_balance("USDT")

			stop_loss_pct = risk_service.STRATEGY_CONFIG[symbol].get("stop_loss", 0.02)
			total_loss_pct = risk_service.RISK_CONFIG.get("default_trade_loss_pct", 0.01)

			# --- Адаптивная аллокация ---
			position_size = await risk_service.calculate_position_size(
					symbol=symbol,
					deposit=deposit,
					entry_price=price or 1.0,
					stop_loss_pct=stop_loss_pct,
					strength=signal_strength,
					ml_confidence=confidence_score
			)
			amount = position_size * (0.5 + confidence_score)

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
					trade = TradeORM(
						symbol=symbol,
						side=side,
						amount=0.0,
						price=price or 0.0,
						status="cancelled",
						risk_reason="Risk validation failed"
					)
					risk_service.db_session.add(trade)
					await risk_service.db_session.commit()
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
		risk_service.db_session.add(trade)
		await risk_service.db_session.commit()

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
		logger.error(f"❌ OCO order error: {e}")
		await broker.publish_telegram({
			"type": "error",
			"error": f"OCO order failed: {e}"
		})
		return {"error": str(e)}

