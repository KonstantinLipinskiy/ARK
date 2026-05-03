import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import torch
import torch.nn as nn
import torch.optim as optim
from tensorflow import keras
from transformers import pipeline

class MLService:
	def __init__(self):
		self.model = None

	def prepare_data(self, trades: list[dict]) -> pd.DataFrame:
		"""Преобразует список сделок в DataFrame для обучения и добавляет derived features."""
		df = pd.DataFrame(trades)
		if "timestamp" in df.columns:
			df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
		# пример расширения признаков
		if "high" in df.columns and "low" in df.columns and "close" in df.columns:
			df["atr"] = (df["high"] - df["low"]).rolling(window=14).mean()
		return df

	# === Scikit-learn ===
	def train_sklearn(self, df: pd.DataFrame):
		"""Пример обучения модели Scikit-learn."""
		X = df[["ema", "rsi", "macd", "hour", "atr"]].fillna(0)
		y = df["result"]
		X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
		self.model = RandomForestClassifier()
		self.model.fit(X_train, y_train)
		return self.model.score(X_test, y_test)

	def predict_signal(self, features: dict) -> float:
		"""Прогноз силы сигнала (вероятность успеха)."""
		if not self.model:
			raise ValueError("Model not trained")
		X = pd.DataFrame([features])
		return self.model.predict_proba(X)[0][1]

	# === PyTorch ===
	def train_pytorch(self, df: pd.DataFrame):
		"""Пример обучения простой нейросети на PyTorch."""
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
		return model

	# === TensorFlow/Keras ===
	def train_tensorflow(self, df: pd.DataFrame):
		"""Пример обучения модели на TensorFlow/Keras."""
		X = df[["ema", "rsi", "macd"]].values
		y = df["result"].values

		model = keras.Sequential([
			keras.layers.Dense(16, activation="relu", input_shape=(3,)),
			keras.layers.Dense(2, activation="softmax")
		])
		model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
		model.fit(X, y, epochs=50, verbose=0)

		self.model = model
		return model

	# === HuggingFace Transformers ===
	def analyze_news(self, text: str) -> dict:
		"""Пример использования HuggingFace для анализа новостей."""
		sentiment = pipeline("sentiment-analysis")
		return sentiment(text)[0]

	# === Сохранение/загрузка моделей ===
	def save_model(self, path: str):
		"""Сохраняет модель на диск."""
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
		"""Загружает модель с диска."""
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
