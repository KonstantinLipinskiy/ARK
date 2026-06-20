# tests/test_metrics.py
import pytest
from app.utils import metrics
from app.utils.logger import metrics_logger

def test_export_report_metrics_success(caplog):
	"""Проверка успешного экспорта метрик отчётов вызывает metrics_logger.info"""
	caplog.set_level("INFO", logger=metrics_logger.name)

	# Вызов функции с корректными данными
	metrics.export_report_metrics(search_accuracy=0.95, latency=0.123)

	# Проверяем, что в логах есть запись уровня INFO
	assert any(
		"✅ Экспорт метрик отчётов" in message
		for message in caplog.messages
	)

def test_export_report_metrics_error(monkeypatch, caplog):
	"""Проверка ошибки экспорта метрик вызывает metrics_logger.error"""
	caplog.set_level("ERROR", logger=metrics_logger.name)

	# Подменяем Gauge.set чтобы вызвать исключение
	def fake_set(*args, **kwargs):
		raise RuntimeError("Test error")

	monkeypatch.setattr(metrics.REPORT_SEARCH_ACCURACY, "set", fake_set)

	# Вызов функции с ошибкой
	metrics.export_report_metrics(search_accuracy=0.95, latency=0.123)

	# Проверяем, что в логах есть запись уровня ERROR
	assert any(
		"❌ Ошибка экспорта метрик отчётов" in message
		for message in caplog.messages
	)

def test_export_ml_metrics_success(caplog):
	"""Проверка успешного экспорта ML метрик вызывает metrics_logger.info"""
	caplog.set_level("INFO", logger=metrics_logger.name)

	metrics.export_ml_metrics(
		metrics={"accuracy": 0.9, "loss": 0.1, "precision": 0.85, "recall": 0.88},
		epoch_losses=[0.1, 0.08, 0.07],
		training_time=12.5,
		learning_rate=0.001
	)

	assert any(
		"✅ Экспорт ML метрик" in message
		for message in caplog.messages
	)

def test_export_ml_metrics_error(monkeypatch, caplog):
	"""Проверка ошибки экспорта ML метрик вызывает metrics_logger.error"""
	caplog.set_level("ERROR", logger=metrics_logger.name)

	def fake_set(*args, **kwargs):
		raise RuntimeError("Test ML error")

	monkeypatch.setattr(metrics.ml_accuracy, "set", fake_set)

	metrics.export_ml_metrics(metrics={"accuracy": 0.9})

	assert any(
		"❌ Ошибка экспорта ML метрик" in message
		for message in caplog.messages
	)
