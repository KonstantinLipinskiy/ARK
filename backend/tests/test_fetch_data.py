# tests/test_fetch_data.py
import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from scripts.fetch_data import update_csv

TEST_OUT_DIR = "test_data"

@pytest.fixture(scope="function", autouse=True)
def setup_and_cleanup():
	os.makedirs(TEST_OUT_DIR, exist_ok=True)
	yield
	# очистка после теста
	for f in os.listdir(TEST_OUT_DIR):
		os.remove(os.path.join(TEST_OUT_DIR, f))
	os.rmdir(TEST_OUT_DIR)

def test_update_csv_success(caplog):
	"""Проверяем успешное создание CSV и логирование INFO."""
	mock_ohlcv = [
		[1620000000000, 100, 110, 90, 105, 1000],
		[1620003600000, 105, 115, 95, 110, 1200],
	]
	with patch("ccxt.binance") as mock_binance:
		mock_exchange = MagicMock()
		mock_exchange.fetch_ohlcv.return_value = mock_ohlcv
		mock_binance.return_value = mock_exchange

		update_csv("BTC/USDT", "1h", 1, TEST_OUT_DIR)

	files = os.listdir(TEST_OUT_DIR)
	assert any("BTCUSDT_1h.csv" in f for f in files)
	assert "✅ Updated" in caplog.text

def test_update_csv_empty_data(caplog):
	"""Проверяем, что при пустых данных файл не создаётся и логируется WARNING."""
	with patch("ccxt.binance") as mock_binance:
		mock_exchange = MagicMock()
		mock_exchange.fetch_ohlcv.return_value = []
		mock_binance.return_value = mock_exchange

		update_csv("BTC/USDT", "1h", 1, TEST_OUT_DIR)

	files = os.listdir(TEST_OUT_DIR)
	assert len(files) == 0
	assert "⚠️ Нет данных" in caplog.text

def test_update_csv_api_error(caplog):
	"""Проверяем, что при ошибке API логируется ERROR."""
	with patch("ccxt.binance") as mock_binance:
		mock_exchange = MagicMock()
		mock_exchange.fetch_ohlcv.side_effect = Exception("API error")
		mock_binance.return_value = mock_exchange

		update_csv("BTC/USDT", "1h", 1, TEST_OUT_DIR)

	files = os.listdir(TEST_OUT_DIR)
	assert len(files) == 0
	assert "❌ Ошибка обновления данных" in caplog.text
