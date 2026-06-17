# app/utils/export.py
import pandas as pd
from app.utils.logger import logger

def export_to_excel(all_metrics: dict, all_results: dict, filename: str = "backtest_summary.xlsx"):
	"""
	Экспорт метрик и сделок в Excel.
	Используется только для отладки, если settings.DEBUG_EXPORT = True.
	"""
	try:
		with pd.ExcelWriter(filename, engine="openpyxl") as writer:
			# Метрики
			df_report = pd.DataFrame.from_dict(all_metrics, orient="index")
			df_report.to_excel(writer, sheet_name="Metrics")

			# Сделки по каждой паре и стратегии
			for key, trades in all_results.items():
				df_trades = pd.DataFrame(trades)
				sheet_name = key.replace("/", "_")[:30]  # Excel ограничивает имя листа 31 символом
				df_trades.to_excel(writer, sheet_name=sheet_name)

		logger.info(f"✅ Excel отчёт сохранён: {filename}")
	except Exception as e:
		logger.error(f"❌ Ошибка экспорта в Excel: {e}")
