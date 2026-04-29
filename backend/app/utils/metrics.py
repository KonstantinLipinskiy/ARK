from typing import List, Dict, Union
import math

def _extract_profit(trade: Union[Dict, object]) -> float:
	"""Универсальный доступ к профиту (dict или ORM)."""
	return trade["profit"] if isinstance(trade, dict) else getattr(trade, "profit", 0.0)

def calculate_profit(trades: List[Union[Dict, object]]) -> float:
	return sum(_extract_profit(trade) for trade in trades)

def calculate_winrate(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	wins = sum(1 for trade in trades if _extract_profit(trade) > 0)
	return wins / len(trades)

def calculate_average_profit(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	return calculate_profit(trades) / len(trades)

def calculate_max_drawdown(trades: List[Union[Dict, object]]) -> float:
	equity = 0.0
	max_equity = 0.0
	max_drawdown = 0.0
	for trade in trades:
		equity += _extract_profit(trade)
		max_equity = max(max_equity, equity)
		drawdown = max_equity - equity
		max_drawdown = max(max_drawdown, drawdown)
	return max_drawdown

def calculate_sharpe_ratio(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	profits = [_extract_profit(t) for t in trades]
	avg = sum(profits) / len(profits)
	std = math.sqrt(sum((p - avg) ** 2 for p in profits) / len(profits))
	return avg / std if std > 0 else 0.0

def calculate_sortino_ratio(trades: List[Union[Dict, object]]) -> float:
	if not trades:
		return 0.0
	profits = [_extract_profit(t) for t in trades]
	avg = sum(profits) / len(profits)
	downside = [p for p in profits if p < 0]
	if not downside:
		return float("inf")
	std_down = math.sqrt(sum(p ** 2 for p in downside) / len(downside))
	return avg / std_down if std_down > 0 else 0.0

def calculate_profit_factor(trades: List[Union[Dict, object]]) -> float:
	gains = sum(_extract_profit(t) for t in trades if _extract_profit(t) > 0)
	losses = abs(sum(_extract_profit(t) for t in trades if _extract_profit(t) < 0))
	return gains / losses if losses > 0 else float("inf")

def calculate_max_consecutive(trades: List[Union[Dict, object]]) -> Dict[str, int]:
	max_wins = max_losses = 0
	current_wins = current_losses = 0
	for trade in trades:
		if _extract_profit(trade) > 0:
			current_wins += 1
			max_wins = max(max_wins, current_wins)
			current_losses = 0
		else:
			current_losses += 1
			max_losses = max(max_losses, current_losses)
			current_wins = 0
	return {"max_consecutive_wins": max_wins, "max_consecutive_losses": max_losses}

def calculate_metrics(trades: List[Union[Dict, object]]) -> Dict:
	return {
		"total_profit": calculate_profit(trades),
		"winrate": calculate_winrate(trades),
		"average_profit": calculate_average_profit(trades),
		"max_drawdown": calculate_max_drawdown(trades),
		"sharpe_ratio": calculate_sharpe_ratio(trades),
		"sortino_ratio": calculate_sortino_ratio(trades),
		"profit_factor": calculate_profit_factor(trades),
		**calculate_max_consecutive(trades),
		"trades_count": len(trades)
	}
