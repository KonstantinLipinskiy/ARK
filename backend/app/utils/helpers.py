import datetime
import json
import hashlib

# Форматирование дат
def format_timestamp(ts: float) -> str:
	"""Преобразует UNIX timestamp в строку ISO."""
	return datetime.datetime.fromtimestamp(ts).isoformat()

# Хэширование строк (например, для ID сигналов)
def generate_hash(value: str) -> str:
	"""Создаёт SHA256 хэш из строки."""
	return hashlib.sha256(value.encode()).hexdigest()

# Загрузка JSON из строки/файла
def load_json(data: str) -> dict:
	"""Безопасная загрузка JSON."""
	try:
		return json.loads(data)
	except json.JSONDecodeError:
		return {}

# Ограничение числа знаков после запятой
def round_value(value: float, decimals: int = 4) -> float:
	"""Округляет число до N знаков."""
	return round(value, decimals)

# Проверка положительности числа
def is_positive(value: float) -> bool:
	"""Возвращает True, если число положительное."""
	return value > 0
