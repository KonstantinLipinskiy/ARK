# tests/test_export.py
import os
import glob
import pandas as pd
import pytest
from datetime import datetime
from app.utils.export import export_to_excel
from app.config import settings

@pytest.fixture
def cleanup_files():
	"""Удаляем все тестовые Excel файлы после теста"""
	yield
	for f in glob.glob("backtest_summary*.xlsx"):
		try:
			os.remove(f)
		except FileNotFoundError:
			pass

def test_export_empty_data(cleanup_files):
	"""Проверка: при пустых данных файл не создаётся"""
	export_to_excel({}, {})
	files = glob.glob("backtest_summary*.xlsx")
	assert len(files) == 0, "Файл не должен создаваться при пустых данных"

def test_export_with_data(cleanup_files):
	"""Проверка: при нормальных данных создаются листы"""
	metrics = {"Sharpe": 1.25, "Winrate": 0.55}
	results = {
		"BTC/USDT": [
			{"entry": 30000, "exit": 31000, "profit": 1000},
			{"entry": 31000, "exit": 30500, "profit": -500},
		]
	}

	export_to_excel(metrics, results)

	files = glob.glob("backtest_summary*.xlsx")
	assert len(files) == 1, "Файл должен быть создан"

	# Проверяем, что листы существуют
	filename = files[0]
	xls = pd.ExcelFile(filename)
	assert "Metrics" in xls.sheet_names
	assert "BTC_USDT" in xls.sheet_names

def test_export_filename_with_timestamp(cleanup_files, monkeypatch):
	"""Проверка: имя файла соответствует настройкам (с timestamp или без)"""
	# Включаем timestamp
	monkeypatch.setattr(settings, "EXPORT_TIMESTAMP", True)
	metrics = {"Sharpe": 1.25}
	results = {"ETH/USDT": [{"entry": 2000, "exit": 2100, "profit": 100}]}

	export_to_excel(metrics, results)

	files = glob.glob("backtest_summary*.xlsx")
	assert len(files) == 0, "Файл без timestamp не должен создаваться"

	files = glob.glob("backtest_summary_*.xlsx")
	assert len(files) == 1, "Файл с timestamp должен быть создан"

	filename = files[0]
	assert "backtest_summary_" in filename
	assert filename.endswith(".xlsx")
