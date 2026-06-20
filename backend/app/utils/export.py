# app/utils/export.py
import pandas as pd
from app.utils.logger import logger
from app.config import settings
from app.utils.helpers import generate_export_filename, autofit_columns

def export_to_excel(all_metrics: dict, all_results: dict, filename: str = None):
	"""
	Экспорт метрик и сделок в Excel.
	Используется только для отладки, если settings.DEBUG_EXPORT = True.
	"""
	try:
		# --- Проверка пустых данных ---
		if not all_metrics and not all_results:
			logger.warning("⚠️ Нет данных для экспорта, файл не создан")
			return

		# --- Гибкое имя файла ---
		if not filename:
			filename = generate_export_filename(
				base_name=getattr(settings, "EXPORT_FILENAME", "backtest_summary.xlsx"),
				use_timestamp=getattr(settings, "EXPORT_TIMESTAMP", True)
			)

		with pd.ExcelWriter(filename, engine="openpyxl") as writer:
			# Метрики
			if all_metrics:
				df_report = pd.DataFrame.from_dict(all_metrics, orient="index")
				df_report.to_excel(writer, sheet_name="Metrics", float_format="%.4f")

				# --- Форматирование: автоширина колонок ---
				worksheet = writer.sheets["Metrics"]
				autofit_columns(worksheet)

			# Сделки по каждой паре и стратегии
			for key, trades in all_results.items():
				if not trades:
					continue
				df_trades = pd.DataFrame(trades)
				sheet_name = key.replace("/", "_")[:30]  # Excel ограничивает имя листа 31 символом
				df_trades.to_excel(writer, sheet_name=sheet_name, float_format="%.4f")

				# --- Форматирование: автоширина колонок ---
				worksheet = writer.sheets[sheet_name]
				autofit_columns(worksheet)

		logger.info(f"✅ Excel отчёт сохранён: {filename}")
	except Exception as e:
		logger.error(f"❌ Ошибка экспорта в Excel: {e}")
