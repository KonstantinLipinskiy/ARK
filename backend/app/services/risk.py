from app.config import STRATEGY_CONFIG, RISK_CONFIG

# Расчёт размера позиции
def calculate_position_size(deposit: float, entry_price: float, stop_loss_pct: float) -> float:
	risk_amount = deposit * RISK_CONFIG["max_risk_per_trade"]
	stop_loss_amount = entry_price * stop_loss_pct
	position_size = risk_amount / stop_loss_amount
	return position_size

# Применение стоп-лосса
def apply_stop_loss(entry_price: float, stop_loss_pct: float) -> float:
	return entry_price * (1 - stop_loss_pct)

# Применение тейк-профита (многоуровневого)
def apply_take_profit(entry_price: float, targets: list[float]) -> list[float]:
	return [entry_price * (1 + tp) for tp in targets]

# Трейлинг-стоп
def apply_trailing_stop(current_price: float, stop_price: float, trailing_pct: float) -> float:
	new_stop = current_price * (1 - trailing_pct)
	return max(stop_price, new_stop)

# Проверка дневного лимита убытков
def check_daily_loss(total_loss_pct: float) -> bool:
	return total_loss_pct <= RISK_CONFIG["max_daily_loss"]

# Проверка количества открытых сделок
def check_open_trades(open_trades: int) -> bool:
	return open_trades < RISK_CONFIG["max_open_trades"]
