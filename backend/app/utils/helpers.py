import datetime
import json
import hashlib
import uuid

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
	except ValueError:
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

def safe_divide(a: float, b: float) -> float:
	"""Деление с защитой от деления на ноль."""
	try:
		return a / b if b != 0 else 0.0
	except Exception:
		return 0.0

def percent_change(a: float, b: float) -> float:
	"""Процентное изменение между двумя значениями."""
	try:
		if a == 0:
			return 0.0
		return ((b - a) / a) * 100
	except Exception:
		return 0.0

def safe_float(value) -> float:
	"""Преобразование строки/значения в число с защитой от ошибок."""
	try:
		return float(value)
	except (ValueError, TypeError):
		return 0.0

# --- Работа с JSON ---
def load_json(data: str) -> dict:
	"""Безопасная загрузка JSON."""
	try:
		return json.loads(data)
	except json.JSONDecodeError:
		return {}

def dump_json(obj: dict) -> str:
	"""Безопасная сериализация в строку."""
	try:
		return json.dumps(obj)
	except Exception:
		return "{}"

def pretty_json(obj: dict) -> str:
	"""Форматированный JSON для логов."""
	try:
		return json.dumps(obj, indent=4, ensure_ascii=False)
	except Exception:
		return "{}"

# --- Утилиты для мониторинга ---
def hash_signal_key(signal: dict) -> str:
	"""Уникальный ключ для метрик Prometheus по сигналу."""
	base = f"{signal.get('symbol', '')}_{signal.get('indicator', '')}_{signal.get('direction', '')}"
	return short_hash(base, length=12)
