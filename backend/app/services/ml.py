# app/services/ml.py
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
import torch
import torch.nn as nn
import torch.optim as optim
from tensorflow import keras
from transformers import pipeline
from app.db.vector import VectorDB
from app.utils.logger import logger

class MLService:
	def __init__(self):
		self.model = None
		self.vector_db = VectorDB()

	def prepare_data(self, trades: list[dict]) -> pd.DataFrame:
		"""Преобразует список сделок в DataFrame для обучения и добавляет derived features."""
		df = pd.DataFrame(trades)

		# Время сделки
		if "timestamp" in df.columns:
			df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour

		# ATR
		if {"high", "low", "close"} <= set(df.columns):
			df["atr"] = (df["high"] - df["low"]).rolling(window=14).mean()

		# Bollinger Bands
		if "close" in df.columns:
			df["bollinger_ma"] = df["close"].rolling(window=20).mean()
			df["bollinger_std"] = df["close"].rolling(window=20).std()
			df["bollinger_upper"] = df["bollinger_ma"] + (df["bollinger_std"] * 2)
			df["bollinger_lower"] = df["bollinger_ma"] - (df["bollinger_std"] * 2)

		# OBV (On-Balance Volume)
		if {"close", "volume"} <= set(df.columns):
			df["obv"] = (df["volume"] * ((df["close"].diff() > 0).astype(int) -
													(df["close"].diff() < 0).astype(int))).cumsum()

		# Объёмы
		if "volume" in df.columns:
			df["volume_ma"] = df["volume"].rolling(window=20).mean()

		# Новостной сентимент (пример: берём из VectorDB)
		try:
			self.vector_db.use_collection("news")
			sentiments = []
			for _, row in df.iterrows():
					text = row.get("news", "")
					if text:
						sentiment = pipeline("sentiment-analysis")(text)[0]
						sentiments.append(sentiment["score"] if sentiment["label"] == "POSITIVE" else -sentiment["score"])
					else:
						sentiments.append(0.0)
			df["news_sentiment"] = sentiments
		except Exception as e:
			logger.error(f"Ошибка добавления новостного сентимента: {e}")
			df["news_sentiment"] = 0.0

		return df

	def train(self, df: pd.DataFrame, model_type: str = "sklearn") -> dict:
		"""Единый метод обучения модели. Возвращает метрики обучения."""
		if model_type == "sklearn":
			X = df[["ema", "rsi", "macd", "hour", "atr",
						"bollinger_upper", "bollinger_lower", "obv",
						"volume_ma", "news_sentiment"]].fillna(0)
			y = df["result"]
			X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
			self.model = RandomForestClassifier()
			self.model.fit(X_train, y_train)
			y_pred = self.model.predict(X_test)
			return {
					"accuracy": accuracy_score(y_test, y_pred),
					"precision": precision_score(y_test, y_pred, average="binary"),
					"recall": recall_score(y_test, y_pred, average="binary")
			}

		elif model_type == "pytorch":
			X = torch.tensor(df[["ema", "rsi", "macd"]].values, dtype=torch.float32)
			y = torch.tensor(df["result"].values, dtype=torch.long)
			model = nn.Sequential(
					nn.Linear(3, 16),
					nn.ReLU(),
					nn.Linear(16, 2)
			)
			optimizer = optim.Adam(model.parameters(), lr=0.001)
			loss_fn = nn.CrossEntropyLoss()
			for epoch in range(50):
					optimizer.zero_grad()
					output = model(X)
					loss = loss_fn(output, y)
					loss.backward()
					optimizer.step()
			self.model = model
			with torch.no_grad():
					preds = model(X).argmax(dim=1)
					acc = (preds == y).float().mean().item()
			return {"accuracy": acc, "precision": None, "recall": None}

		elif model_type == "tensorflow":
			X = df[["ema", "rsi", "macd"]].values
			y = df["result"].values
			model = keras.Sequential([
					keras.layers.Dense(16, activation="relu", input_shape=(3,)),
					keras.layers.Dense(2, activation="softmax")
			])
			model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
			history = model.fit(X, y, epochs=50, verbose=0)
			self.model = model
			acc = history.history["accuracy"][-1]
			return {"accuracy": acc, "precision": None, "recall": None}

		else:
			raise ValueError("Неизвестный тип модели")

	def predict_signal(self, features: dict) -> float:
		if not self.model:
			raise ValueError("Model not trained")
		X = pd.DataFrame([features])
		return self.model.predict_proba(X)[0][1]

	def predict_with_confidence(self, features: dict) -> dict:
		if not self.model:
			raise ValueError("Model not trained")
		X = pd.DataFrame([features])
		proba = self.model.predict_proba(X)[0]
		confidence_score = abs(proba[1] - proba[0])
		result = {"success_probability": proba[1], "confidence_score": confidence_score}
		try:
			self.save_signal_embedding(features, signal_id=hash(str(features)))
		except Exception as e:
			logger.error(f"Ошибка сохранения эмбеддинга сигнала: {e}")
		return result

	def get_confidence_score(self, features: dict) -> float:
		result = self.predict_with_confidence(features)
		return result["confidence_score"]

	def analyze_news(self, text: str) -> dict:
		sentiment = pipeline("sentiment-analysis")
		result = sentiment(text)[0]
		try:
			self.vector_db.use_collection("news")
			vector = [float(hash(text) % 1000) / 1000.0] * 768
			payload = {"id": hash(text), "text": text, "label": result["label"], "score": result["score"]}
			self.vector_db.insert_vector(vector, payload)
		except Exception as e:
			logger.error(f"Ошибка сохранения эмбеддинга новости: {e}")
		return result

	def save_model(self, path: str):
		if self.model is None:
			raise ValueError("Нет обученной модели для сохранения")
		if isinstance(self.model, RandomForestClassifier):
			joblib.dump(self.model, path)
		elif isinstance(self.model, nn.Module):
			torch.save(self.model.state_dict(), path)
		elif isinstance(self.model, keras.Model):
			self.model.save(path)
		else:
			raise TypeError("Неизвестный тип модели")

	def load_model(self, path: str, model_type: str):
		if model_type == "sklearn":
			self.model = joblib.load(path)
		elif model_type == "pytorch":
			model = nn.Sequential(
					nn.Linear(3, 16),
					nn.ReLU(),
					nn.Linear(16, 2)
			)
			model.load_state_dict(torch.load(path))
			self.model = model
		elif model_type == "tensorflow":
			self.model = keras.models.load_model(path)
		else:
			raise ValueError("Неизвестный тип модели")

	def save_signal_embedding(self, features: dict, signal_id: int):
		try:
			self.vector_db.use_collection("signals")
			vector = [float(v) for v in features.values()] * (768 // len(features))
			payload = {"id": signal_id, "features": features}
			self.vector_db.insert_vector(vector, payload)
			logger.info(f"Эмбеддинг сигнала сохранён: {payload}")
		except Exception as e:
			logger.error(f"Ошибка сохранения эмбеддинга сигнала: {e}")
