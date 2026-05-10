# app/utils/helpers.py
import datetime
import json
import hashlib
import uuid
from typing import Any, Dict, Optional

# --- Работа с датами и временем ---
def format_timestamp(ts: float) -> str:
	"""Преобразует UNIX timestamp в строку ISO."""
	return datetime.datetime.fromtimestamp(ts).isoformat()

def now_utc() -> datetime.datetime:
	"""Возвращает текущее время в UTC."""
	return datetime.datetime.utcnow()

def parse_iso(date_str: str) -> datetime.datetime:
	"""Преобразует ISO строку обратно в datetime."""
	try:
		return datetime.datetime.fromisoformat(date_str)
	except (ValueError, TypeError):
		return datetime.datetime.utcnow()

# --- Работа с идентификаторами ---
def generate_hash(value: str) -> str:
	"""Создаёт SHA256 хэш из строки."""
	return hashlib.sha256(value.encode()).hexdigest()

def short_hash(value: str, length: int = 8) -> str:
	"""Создаёт сокращённый хэш для удобного отображения."""
	return generate_hash(value)[:length]

def generate_uuid() -> str:
	"""Генерация UUID для сделок/сигналов."""
	return str(uuid.uuid4())

# --- Работа с числами ---
def round_value(value: float, decimals: int = 4) -> float:
	"""Округляет число до N знаков."""
	return round(value, decimals)

def is_positive(value: float) -> bool:
	"""Возвращает True, если число положительное."""
	return value > 0

def safe_divide(a: Optional[float], b: Optional[float]) -> float:
	"""Деление с защитой от деления на ноль."""
	try:
		if b is None or b == 0:
			return 0.0
		return a / b if a is not None else 0.0
	except Exception:
		return 0.0

def percent_change(a: Optional[float], b: Optional[float]) -> float:
	"""Процентное изменение между двумя значениями."""
	try:
		if a is None or a == 0:
			return 0.0
		return ((b - a) / a) * 100
	except Exception:
		return 0.0

def safe_float(value: Any) -> float:
	"""Преобразование строки/значения в число с защитой от ошибок."""
	try:
		return float(value)
	except (ValueError, TypeError):
		return 0.0

# --- Работа с JSON ---
def load_json(data: str) -> Dict[str, Any]:
	"""Безопасная загрузка JSON."""
	try:
		return json.loads(data)
	except json.JSONDecodeError:
		return {}

def dump_json(obj: Dict[str, Any]) -> str:
	"""Безопасная сериализация в строку."""
	try:
		return json.dumps(obj, ensure_ascii=False, default=str)
	except Exception:
		return "{}"

def pretty_json(obj: Dict[str, Any]) -> str:
	"""Форматированный JSON для логов."""
	try:
		return json.dumps(obj, indent=4, ensure_ascii=False, default=str)
	except Exception:
		return "{}"

# --- Утилиты для мониторинга ---
def hash_signal_key(signal: Dict[str, Any]) -> str:
	"""
	Уникальный ключ для метрик Prometheus по сигналу.
	Можно расширить: добавить user_id или strategy.
	"""
	base = f"{signal.get('symbol', '')}_{signal.get('indicator', '')}_{signal.get('direction', '')}"
	return short_hash(base, length=12)
