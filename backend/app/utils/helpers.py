#app/utils/helpers.py
import datetime
import json
import hashlib
import uuid
from typing import Any, Dict, Optional
from openpyxl.utils import get_column_letter
from app.utils.logger import logger

# --- Работа с датами и временем ---
def format_timestamp(ts: float) -> str:
	"""Преобразует UNIX timestamp в строку ISO (UTC)."""
	return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()

def now_utc() -> datetime.datetime:
	"""Возвращает текущее время в UTC с tzinfo."""
	return datetime.datetime.now(datetime.timezone.utc)

def parse_iso(date_str: str) -> Optional[datetime.datetime]:
	"""Преобразует ISO строку обратно в datetime. Возвращает None при ошибке."""
	try:
		return datetime.datetime.fromisoformat(date_str)
	except (ValueError, TypeError) as e:
		logger.error(f"Ошибка парсинга ISO даты: {e}", extra={"operation": "helpers", "collection": "dates"})
		return None

# --- Работа с идентификаторами ---
def generate_hash(value: str) -> str:
	"""Создаёт SHA256 хэш из строки."""
	if not isinstance(value, str):
		value = str(value)
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
	if decimals < 0:
		return value
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
	except Exception as e:
		logger.error(f"Ошибка safe_divide: {e}", extra={"operation": "helpers", "collection": "math"})
		return 0.0

def percent_change(a: Optional[float], b: Optional[float]) -> float:
	"""Процентное изменение между двумя значениями."""
	try:
		if a is None or a == 0 or b is None:
			return 0.0
		return ((b - a) / a) * 100
	except Exception as e:
		logger.error(f"Ошибка percent_change: {e}", extra={"operation": "helpers", "collection": "math"})
		return 0.0

def safe_float(value: Any) -> float:
	"""Преобразование строки/значения в число с защитой от ошибок."""
	try:
		return float(value)
	except (ValueError, TypeError) as e:
		logger.error(f"Ошибка safe_float: {e}", extra={"operation": "helpers", "collection": "math"})
		return 0.0

# --- Работа с JSON ---
def load_json(data: str) -> Dict[str, Any]:
	"""Безопасная загрузка JSON."""
	try:
		return json.loads(data)
	except json.JSONDecodeError as e:
		logger.error(f"Ошибка load_json: {e}", extra={"operation": "helpers", "collection": "json"})
		return {}

def dump_json(obj: Dict[str, Any]) -> str:
	"""Безопасная сериализация в строку."""
	try:
		return json.dumps(obj, ensure_ascii=False, default=str)
	except Exception as e:
		logger.error(f"Ошибка dump_json: {e}", extra={"operation": "helpers", "collection": "json"})
		return "{}"

def pretty_json(obj: Dict[str, Any]) -> str:
	"""Форматированный JSON для логов."""
	try:
		return json.dumps(obj, indent=4, ensure_ascii=False, default=str)
	except Exception as e:
		logger.error(f"Ошибка pretty_json: {e}", extra={"operation": "helpers", "collection": "json"})
		return "{}"

# --- Утилиты для мониторинга ---
def hash_signal_key(signal: Dict[str, Any]) -> str:
	"""
	Уникальный ключ для метрик Prometheus по сигналу.
	Можно расширить: добавить user_id или strategy.
	"""
	base = f"{signal.get('symbol', '')}_{signal.get('indicator', '')}_{signal.get('direction', '')}"
	return short_hash(base, length=12)

# --- Утилиты для экспорта ---
def generate_export_filename(base_name: str = "backtest_summary.xlsx", use_timestamp: bool = True) -> str:
	"""Генерация имени файла экспорта с опциональным timestamp."""
	if use_timestamp:
		timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
		return base_name.replace(".xlsx", f"_{timestamp}.xlsx")
	return base_name

def autofit_columns(worksheet) -> None:
	"""Автоширина колонок для Excel листа."""
	for col in worksheet.columns:
		max_length = 0
		col_letter = get_column_letter(col[0].column)
		for cell in col:
			try:
				if cell.value:
					max_length = max(max_length, len(str(cell.value)))
			except Exception as e:
				logger.error(f"Ошибка autofit_columns: {e}", extra={"operation": "helpers", "collection": "excel"})
		adjusted_width = (max_length + 2)
		worksheet.column_dimensions[col_letter].width = adjusted_width
