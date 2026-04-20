from typing import List, Dict

def calculate_profit(trades: List[Dict]) -> float:
	"""Суммарный профит по всем сделкам."""
	return sum(trade["profit"] for trade in trades)

def calculate_winrate(trades: List[Dict]) -> float:
	"""Процент успешных сделок."""
	if not trades:
		return 0.0
	wins = sum(1 for trade in trades if trade["profit"] > 0)
	return wins / len(trades)

def calculate_average_profit(trades: List[Dict]) -> float:
	"""Средняя прибыль на сделку."""
	if not trades:
		return 0.0
	return sum(trade["profit"] for trade in trades) / len(trades)

def calculate_max_drawdown(trades: List[Dict]) -> float:
	"""Максимальная просадка (на основе equity curve)."""
	equity = 0.0
	max_equity = 0.0
	max_drawdown = 0.0

	for trade in trades:
		equity += trade["profit"]
		max_equity = max(max_equity, equity)
		drawdown = (max_equity - equity)
		max_drawdown = max(max_drawdown, drawdown)

	return max_drawdown

def calculate_metrics(trades: List[Dict]) -> Dict:
	"""Комплексный расчёт метрик."""
	return {
		"total_profit": calculate_profit(trades),
		"winrate": calculate_winrate(trades),
		"average_profit": calculate_average_profit(trades),
		"max_drawdown": calculate_max_drawdown(trades),
		"trades_count": len(trades)
	}
