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
import numpy as np
from app.db.vector import VectorDB
from app.utils.logger import logger
from app.config import settings
from app.services.exchange import get_ticker, get_order_book, get_mark_price
from app.services.news_loader import NewsLoader


class MLService:
	def __init__(self):
		self.model = None
		self.vector_db = VectorDB()
		self.vector_size = settings.QDRANT_VECTOR_SIZE
		self.news_loader = NewsLoader(newsdata_api_key=settings.NEWSDATA_API_KEY)
		self._seen_ids = set()
		try:
			self.sentiment_pipeline = pipeline("sentiment-analysis")
		except Exception as e:
			logger.error(f"Ошибка инициализации sentiment pipeline: {e}")
			self.sentiment_pipeline = None

	# --- ПОДГОТОВКА ДАННЫХ ---
	def prepare_data(self, trades: list[dict], symbol: str = "bitcoin") -> pd.DataFrame:
		"""
		Принимает список сделок/свечей и готовит признаки для ML-модели.
		Добавляет индикаторы и новостной сентимент.
		"""
		df = pd.DataFrame(trades)

		# --- если нет новостей в df, подтягиваем отдельно ---
		if "news" not in df.columns:
			latest_news = self.news_loader.fetch_newsdata(query=symbol)
			rss_news = self.news_loader.fetch_coindesk_rss()
			all_news = latest_news + rss_news
			if all_news:
				df_news = pd.DataFrame([{"news": text} for text in all_news])
				# фильтруем только df_news
				df_news = df_news[df_news["news"].apply(lambda x: isinstance(x, str) and len(x.strip()) > 20)]
				if not df_news.empty and self.sentiment_pipeline:
					df_news["sentiment"] = df_news["news"].apply(
						lambda text: self.sentiment_pipeline(text)[0]["score"]
						if self.sentiment_pipeline(text)[0]["label"] == "POSITIVE"
						else -self.sentiment_pipeline(text)[0]["score"]
					)
					# агрегируем по времени (например, час) и мержим с df
					df_news = pd.DataFrame([
						{"news": article["title"], "timestamp": pd.to_datetime(article.get("pubDate"))}
						for article in all_news if article.get("pubDate")
					])
					df_news["hour"] = df_news["timestamp"].dt.hour
					sentiment_by_hour = df_news.groupby("hour")["sentiment"].mean().reset_index()
					if "timestamp" in df.columns:
						df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
						df = df.merge(sentiment_by_hour, on="hour", how="left")
						df["news_sentiment"] = df["sentiment"].fillna(0.0).astype(float)
						df.drop(columns=["sentiment"], inplace=True)
					else:
						df["news_sentiment"] = df_news["sentiment"].mean()
				else:
					df["news_sentiment"] = 0.0
		else:
			# если колонка news уже есть в df
			if self.sentiment_pipeline:
				df["news_sentiment"] = df["news"].apply(
					lambda text: self.sentiment_pipeline(text)[0]["score"]
					if self.sentiment_pipeline(text)[0]["label"] == "POSITIVE"
					else -self.sentiment_pipeline(text)[0]["score"]
				)
			else:
				df["news_sentiment"] = 0.0

		# --- индикаторы ---
		if {"high", "low", "close"} <= set(df.columns):
			df["atr"] = (df["high"] - df["low"]).rolling(window=14).mean()

		if "close" in df.columns:
			df["bollinger_ma"] = df["close"].rolling(window=20).mean()
			df["bollinger_std"] = df["close"].rolling(window=20).std()
			df["bollinger_upper"] = df["bollinger_ma"] + (df["bollinger_std"] * 2)
			df["bollinger_lower"] = df["bollinger_ma"] - (df["bollinger_std"] * 2)
			df["bollinger"] = df["close"] - df["bollinger_ma"]

		if {"close", "volume"} <= set(df.columns):
			df["obv"] = (df["volume"] * ((df["close"].diff() > 0).astype(int) -
											(df["close"].diff() < 0).astype(int))).cumsum()

		if {"high", "low", "close"} <= set(df.columns):
			df["stochastic"] = ((df["close"] - df["low"].rolling(14).min()) /
								(df["high"].rolling(14).max() - df["low"].rolling(14).min())) * 100

		if {"close", "volume"} <= set(df.columns):
			df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

		if "close" in df.columns:
			df["ichimoku"] = df["close"].rolling(window=9).mean() - df["close"].rolling(window=26).mean()

		if "volume" in df.columns:
			df["volume_ma"] = df["volume"].rolling(window=20).mean()

		return df

	# --- ДОБАВЛЕНИЕ РЫНОЧНЫХ ДАННЫХ ---
	async def enrich_with_market_data(self, symbol: str, trades: list[dict]) -> pd.DataFrame:
		df = pd.DataFrame(trades)
		ticker = await get_ticker(symbol)
		if "error" not in ticker:
			df["last_price"] = ticker["last"]
			df["bid"] = ticker["bid"]
			df["ask"] = ticker["ask"]
			df["spread"] = ticker["spread"]

		order_book = await get_order_book(symbol, limit=20)
		if "error" not in order_book:
			total_bids = sum([b[1] for b in order_book["bids"]])
			total_asks = sum([a[1] for a in order_book["asks"]])
			df["liquidity_imbalance"] = total_bids - total_asks

		mark = await get_mark_price(symbol)
		if "error" not in mark:
			df["mark_price"] = mark["markPrice"]

		return df

	# --- ОБУЧЕНИЕ ---
	def train(self, df: pd.DataFrame, model_type: str = "sklearn") -> dict:
		if model_type == "sklearn":
			X = df[["ema", "rsi", "macd", "hour", "atr",
					"bollinger_upper", "bollinger_lower", "bollinger",
					"obv", "stochastic", "vwap", "ichimoku",
					"volume", "volume_ma", "news_sentiment",
					"last_price", "spread", "liquidity_imbalance", "mark_price"]].fillna(0)
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

	# --- ПРЕДСКАЗАНИЯ ---
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
			logger.error(f"Ошибка сохранения эмбеддинга сигнала: {e}",
							extra={"operation": "insert", "collection": "signals"})
		return result

	def get_confidence_score(self, features: dict) -> float:
		result = self.predict_with_confidence(features)
		return result["confidence_score"]

	# --- АНАЛИЗ НОВОСТЕЙ ---
	def analyze_news(self, text: str) -> dict:
		if not self.sentiment_pipeline:
			return {"label": "UNKNOWN", "score": 0.0}
		result = self.sentiment_pipeline(text)[0]

		if len(text.strip()) < 20:
			logger.info("Новость слишком короткая, эмбеддинг не сохраняем")
			return result

		try:
			self.vector_db.use_collection("news")
			vector = [float(hash(text) % 1000) / 1000.0] * self.vector_size
			payload = {"id": hash(text), "text": text, "label": result["label"], "score": result["score"]}

			existing = self.vector_db.search_with_filter(vector, {"id": payload["id"]}, top_k=1)
			if existing and not isinstance(existing, dict) and len(existing) > 0:
				logger.info(f"Новость {payload['id']} уже существует в Qdrant — не сохраняем")
				return result

			self.vector_db.insert_vector(vector, payload)
		except Exception as e:
			logger.error(f"Ошибка сохранения эмбеддинга новости: {e}",
							extra={"operation": "insert", "collection": "news"})
		return result

	# --- СОХРАНЕНИЕ/ЗАГРУЗКА МОДЕЛИ ---
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

	# --- СОХРАНЕНИЕ ЭМБЕДДИНГА СИГНАЛА ---
	def save_signal_embedding(self, features: dict, signal_id: int):
		try:
			self.vector_db.use_collection("signals")
			values = [float(v) for v in features.values()]

			if len(values) < 3 or np.allclose(values, 0):
				logger.info(f"Сигнал {signal_id} некорректный")
				return {"status": "skipped", "reason": "invalid features"}

			if np.var(values) < 1e-6:
				logger.info(f"Сигнал {signal_id} имеет слишком низкую дисперсию")
				return {"status": "skipped", "reason": "low variance"}

			vector = (values * (self.vector_size // len(values) + 1))[:self.vector_size]
			payload = {"id": signal_id, "features": features}

			existing = self.vector_db.search_with_filter(vector, {"id": signal_id}, top_k=1)
			if existing and not isinstance(existing, dict) and len(existing) > 0:
				logger.info(f"Сигнал {signal_id} уже существует в Qdrant")
				return {"status": "skipped", "reason": "duplicate"}

			if "id" not in payload or "features" not in payload:
				logger.error(f"Payload некорректный: {payload}")
				return {"status": "skipped", "reason": "invalid payload"}

			self.vector_db.insert_vector(vector, payload)
			logger.info(f"Эмбеддинг сигнала сохранён: {payload}",
						extra={"operation": "insert", "collection": "signals"})
			return {"status": "ok", "id": signal_id}
		except Exception as e:
			logger.error(f"Ошибка сохранения эмбеддинга сигнала: {e}",
							extra={"operation": "insert", "collection": "signals"})
			return {"error": str(e)}
