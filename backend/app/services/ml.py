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
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import StratifiedKFold
import time
from app.db.vector import VectorDB
from app.utils.logger import logger, log_model_load
from app.config import settings
from app.services.exchange import get_ticker, get_order_book, get_mark_price
from app.services.news_loader import NewsLoader
from sklearn.model_selection import train_test_split
from app.utils.metrics import export_ml_metrics, aggregate_cv_metrics, export_cv_metrics
from app.db import crud
from app.db.session import get_session


class MLService:
	def __init__(self):
		self.model = None
		self.vector_db = VectorDB()
		self.vector_size = settings.QDRANT_VECTOR_SIZE
		self.news_loader = NewsLoader(newsdata_api_key=settings.NEWSDATA_API_KEY)
		try:
			self.sentiment_pipeline = pipeline("sentiment-analysis")
			self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
		except Exception as e:
			logger.error(f"Ошибка инициализации sentiment pipeline: {e}")
			self.sentiment_pipeline = None
			self.embedding_model = None


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

			if all_news and self.sentiment_pipeline:
				df_news = pd.DataFrame([
					{
						"title": article.get("title", ""),
						"timestamp": pd.to_datetime(article.get("pubDate")),
						"sentiment": (
							self.sentiment_pipeline(article.get("title"))[0]["score"]
							if self.sentiment_pipeline(article.get("title"))[0]["label"] == "POSITIVE"
							else -self.sentiment_pipeline(article.get("title"))[0]["score"]
						)
					}
					for article in all_news if article.get("pubDate") and isinstance(article.get("title"), str)
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

		# --- новые признаки ---
		if "close" in df.columns:
			# Волатильность (rolling std доходности)
			df["volatility"] = df["close"].pct_change().rolling(window=20).std()

			# Momentum (средняя доходность за окно)
			df["momentum"] = df["close"].pct_change().rolling(window=10).mean()

		if "news_sentiment" in df.columns:
			# Сглаженный сентимент (rolling average)
			df["sentiment_ma"] = df["news_sentiment"].rolling(window=6).mean()

		if {"bid", "ask"} <= set(df.columns):
			# Liquidity ratio
			df["bid_ask_ratio"] = df["bid"] / df["ask"]


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
	def train(self, 
				df: pd.DataFrame, 
				model_type: str = "sklearn", 
				epochs: int = settings.ML_EPOCHS, 
				learning_rate: float = settings.ML_LEARNING_RATE, 
				dropout: float = settings.ML_DROPOUT, 
				hidden_size: int = settings.ML_HIDDEN_SIZE, 
				num_layers: int = settings.ML_NUM_LAYERS,
				use_cross_validation: bool = settings.ML_USE_CV,
				n_splits: int = settings.ML_CV_SPLITS) -> dict:

		# --- общий набор признаков ---
		features = ["ema", "rsi", "macd", "hour", "atr",
					"bollinger_upper", "bollinger_lower", "bollinger",
					"obv", "stochastic", "vwap", "ichimoku",
					"volume", "volume_ma", "news_sentiment",
					"last_price", "spread", "liquidity_imbalance", "mark_price",
					"volatility", "momentum", "sentiment_ma", "bid_ask_ratio"]

		X = df[features].fillna(0)
		y = df["result"]

		if model_type == "sklearn":
			if use_cross_validation:
				kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
				fold_metrics = []

				for train_idx, test_idx in kf.split(X, y):
					X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
					y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

					model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
					model.fit(X_train, y_train)
					y_pred = model.predict(X_test)

					fold_metrics.append({
						"accuracy": accuracy_score(y_test, y_pred),
						"precision": precision_score(y_test, y_pred, average="binary"),
						"recall": recall_score(y_test, y_pred, average="binary"),
						"loss": 0.0
					})

				# усреднение по фолдам
				metrics = aggregate_cv_metrics(fold_metrics)
				self.model = model

				# экспорт в Prometheus
				export_cv_metrics(metrics)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics)

				return metrics

			else:
				X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
				self.model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
				self.model.fit(X_train, y_train)
				y_pred = self.model.predict(X_test)
				metrics = {
					"accuracy": accuracy_score(y_test, y_pred),
					"precision": precision_score(y_test, y_pred, average="binary"),
					"recall": recall_score(y_test, y_pred, average="binary"),
					"loss": 0.0
				}
				export_ml_metrics(metrics, training_time=0, learning_rate=None)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics, training_time=0, learning_rate=None)

				return metrics


		elif model_type == "pytorch_mlp":
			if use_cross_validation:
				kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
				fold_metrics = []

				for train_idx, test_idx in kf.split(X, y):
					X_train, X_test = X.values[train_idx], X.values[test_idx]
					y_train, y_test = y.values[train_idx], y.values[test_idx]

					X_train = torch.tensor(X_train, dtype=torch.float32)
					y_train = torch.tensor(y_train, dtype=torch.long)
					X_test = torch.tensor(X_test, dtype=torch.float32)
					y_test = torch.tensor(y_test, dtype=torch.long)

					model = nn.Sequential(
						nn.Linear(len(features), hidden_size),
						nn.BatchNorm1d(hidden_size),
						nn.ReLU(),
						nn.Dropout(dropout),
						nn.Linear(hidden_size, hidden_size // 2),
						nn.ReLU(),
						nn.Linear(hidden_size // 2, 2)
					)

					optimizer = optim.Adam(model.parameters(), lr=learning_rate)
					loss_fn = nn.CrossEntropyLoss()

					for epoch in range(epochs):
						optimizer.zero_grad()
						output = model(X_train)
						loss = loss_fn(output, y_train)
						loss.backward()
						optimizer.step()

					with torch.no_grad():
						preds = model(X_test).argmax(dim=1).numpy()
						fold_metrics.append({
							"accuracy": accuracy_score(y_test, preds),
							"precision": precision_score(y_test, preds, average="binary"),
							"recall": recall_score(y_test, preds, average="binary"),
							"loss": loss.item()
						})

				# усреднение по фолдам
				metrics = aggregate_cv_metrics(fold_metrics)
				self.model = model

				# экспорт в Prometheus
				export_cv_metrics(metrics)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics)

				return metrics

			else:
				X_train, X_test, y_train, y_test = train_test_split(X.values, y.values, test_size=0.2)
				X_train = torch.tensor(X_train, dtype=torch.float32)
				y_train = torch.tensor(y_train, dtype=torch.long)
				X_test = torch.tensor(X_test, dtype=torch.float32)
				y_test = torch.tensor(y_test, dtype=torch.long)

				model = nn.Sequential(
					nn.Linear(len(features), hidden_size),
					nn.BatchNorm1d(hidden_size),
					nn.ReLU(),
					nn.Dropout(dropout),
					nn.Linear(hidden_size, hidden_size // 2),
					nn.ReLU(),
					nn.Linear(hidden_size // 2, 2)
				)

				optimizer = optim.Adam(model.parameters(), lr=learning_rate)
				loss_fn = nn.CrossEntropyLoss()

				epoch_losses = []
				start_time = time.time()

				for epoch in range(epochs):
					optimizer.zero_grad()
					output = model(X_train)
					loss = loss_fn(output, y_train)
					loss.backward()
					optimizer.step()
					epoch_losses.append(loss.item())

				training_time = time.time() - start_time

				self.model = model
				with torch.no_grad():
					preds = model(X_test).argmax(dim=1).numpy()
					acc = accuracy_score(y_test, preds)
					precision = precision_score(y_test, preds, average="binary")
					recall = recall_score(y_test, preds, average="binary")

				metrics = {"accuracy": acc, "precision": precision, "recall": recall, "loss": loss.item()}
				export_ml_metrics(metrics, epoch_losses=epoch_losses, training_time=training_time, learning_rate=learning_rate)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics, epoch_losses=epoch_losses, training_time=training_time, learning_rate=learning_rate)

				return metrics


		elif model_type == "pytorch_lstm":
			if use_cross_validation:
				kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
				fold_metrics = []

				for train_idx, test_idx in kf.split(X, y):
					X_train, X_test = X.values[train_idx], X.values[test_idx]
					y_train, y_test = y.values[train_idx], y.values[test_idx]

					X_train = torch.tensor(X_train, dtype=torch.float32)
					y_train = torch.tensor(y_train, dtype=torch.long)
					X_test = torch.tensor(X_test, dtype=torch.float32)
					y_test = torch.tensor(y_test, dtype=torch.long)

					timesteps = 30
					if len(X_train) >= timesteps and len(X_test) >= timesteps:
						X_train_seq = X_train.unfold(0, timesteps, 1).permute(0, 2, 1)
						y_train_seq = y_train[timesteps-1:]
						X_test_seq = X_test.unfold(0, timesteps, 1).permute(0, 2, 1)
						y_test_seq = y_test[timesteps-1:]

						class LSTMModel(nn.Module):
							def __init__(self, input_size=len(features), hidden_size=hidden_size, num_layers=num_layers, output_size=2):
								super().__init__()
								self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
								self.fc = nn.Linear(hidden_size, output_size)

							def forward(self, x):
								out, _ = self.lstm(x)
								out = out[:, -1, :]
								return self.fc(out)

						model = LSTMModel()
						optimizer = optim.Adam(model.parameters(), lr=learning_rate)
						loss_fn = nn.CrossEntropyLoss()

						for epoch in range(epochs):
							optimizer.zero_grad()
							output = model(X_train_seq)
							loss = loss_fn(output, y_train_seq)
							loss.backward()
							optimizer.step()

						with torch.no_grad():
							preds = model(X_test_seq).argmax(dim=1).numpy()
							fold_metrics.append({
								"accuracy": accuracy_score(y_test_seq, preds),
								"precision": precision_score(y_test_seq, preds, average="binary"),
								"recall": recall_score(y_test_seq, preds, average="binary"),
								"loss": loss.item()
							})

				metrics = aggregate_cv_metrics(fold_metrics)
				self.model = model

				export_cv_metrics(metrics)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics)

				return metrics

			else:
				X_train, X_test, y_train, y_test = train_test_split(X.values, y.values, test_size=0.2)
				X_train = torch.tensor(X_train, dtype=torch.float32)
				y_train = torch.tensor(y_train, dtype=torch.long)
				X_test = torch.tensor(X_test, dtype=torch.float32)
				y_test = torch.tensor(y_test, dtype=torch.long)

				timesteps = 30
				if len(X_train) >= timesteps and len(X_test) >= timesteps:
					X_train_seq = X_train.unfold(0, timesteps, 1).permute(0, 2, 1)
					y_train_seq = y_train[timesteps-1:]
					X_test_seq = X_test.unfold(0, timesteps, 1).permute(0, 2, 1)
					y_test_seq = y_test[timesteps-1:]

					class LSTMModel(nn.Module):
						def __init__(self, input_size=len(features), hidden_size=hidden_size, num_layers=num_layers, output_size=2):
							super().__init__()
							self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
							self.fc = nn.Linear(hidden_size, output_size)

						def forward(self, x):
							out, _ = self.lstm(x)
							out = out[:, -1, :]
							return self.fc(out)

					model = LSTMModel()
					optimizer = optim.Adam(model.parameters(), lr=learning_rate)
					loss_fn = nn.CrossEntropyLoss()

					epoch_losses = []
					start_time = time.time()

					for epoch in range(epochs):
						optimizer.zero_grad()
						output = model(X_train_seq)
						loss = loss_fn(output, y_train_seq)
						loss.backward()
						optimizer.step()
						epoch_losses.append(loss.item())

					training_time = time.time() - start_time

					self.model = model
					with torch.no_grad():
						preds = model(X_test_seq).argmax(dim=1).numpy()
						acc = accuracy_score(y_test_seq, preds)
						precision = precision_score(y_test_seq, preds, average="binary")
						recall = recall_score(y_test_seq, preds, average="binary")

					metrics = {"accuracy": acc, "precision": precision, "recall": recall, "loss": loss.item()}
					export_ml_metrics(metrics, epoch_losses=epoch_losses, training_time=training_time, learning_rate=learning_rate)

					# 🔹 авто‑логирование обучения
					from app.utils.metrics import log_training_run
					log_training_run(metrics, epoch_losses=epoch_losses, training_time=training_time, learning_rate=learning_rate)

					return metrics
				else:
					raise ValueError("Недостаточно данных для LSTM")


		elif model_type == "tensorflow_gru":
			if use_cross_validation:
				kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
				fold_metrics = []

				for train_idx, test_idx in kf.split(X, y):
					X_train, X_test = X.values[train_idx], X.values[test_idx]
					y_train, y_test = y.values[train_idx], y.values[test_idx]

					timesteps = 30
					if len(X_train) >= timesteps and len(X_test) >= timesteps:
						train_sequences = np.array([X_train[i:i+timesteps] for i in range(len(X_train)-timesteps)])
						train_labels = y_train[timesteps:]
						test_sequences = np.array([X_test[i:i+timesteps] for i in range(len(X_test)-timesteps)])
						test_labels = y_test[timesteps:]

						model = keras.Sequential([
							keras.layers.GRU(hidden_size, return_sequences=True, input_shape=(timesteps, len(features))),
							keras.layers.Dropout(dropout),
							keras.layers.GRU(hidden_size // 2),
							keras.layers.Dense(2, activation="softmax")
						])

						model.compile(optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
										loss="sparse_categorical_crossentropy", metrics=["accuracy"])

						history = model.fit(train_sequences, train_labels, epochs=epochs, verbose=0)
						y_pred = model.predict(test_sequences).argmax(axis=1)

						fold_metrics.append({
							"accuracy": accuracy_score(test_labels, y_pred),
							"precision": precision_score(test_labels, y_pred, average="binary"),
							"recall": recall_score(test_labels, y_pred, average="binary"),
							"loss": np.mean(history.history["loss"])
						})

				metrics = aggregate_cv_metrics(fold_metrics)
				self.model = model

				export_cv_metrics(metrics)

				# 🔹 авто‑логирование обучения
				from app.utils.metrics import log_training_run
				log_training_run(metrics)

				return metrics

			else:
				X_train, X_test, y_train, y_test = train_test_split(X.values, y.values, test_size=0.2)
				timesteps = 30
				if len(X_train) >= timesteps and len(X_test) >= timesteps:
					train_sequences = np.array([X_train[i:i+timesteps] for i in range(len(X_train)-timesteps)])
					train_labels = y_train[timesteps:]
					test_sequences = np.array([X_test[i:i+timesteps] for i in range(len(X_test)-timesteps)])
					test_labels = y_test[timesteps:]

					model = keras.Sequential([
						keras.layers.GRU(hidden_size, return_sequences=True, input_shape=(timesteps, len(features))),
						keras.layers.Dropout(dropout),
						keras.layers.GRU(hidden_size // 2),
						keras.layers.Dense(2, activation="softmax")
					])

					model.compile(optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
									loss="sparse_categorical_crossentropy", metrics=["accuracy"])

					start_time = time.time()
					history = model.fit(train_sequences, train_labels, epochs=epochs, verbose=0)
					training_time = time.time() - start_time

					self.model = model
					y_pred = model.predict(test_sequences).argmax(axis=1)
					acc = accuracy_score(test_labels, y_pred)
					precision = precision_score(test_labels, y_pred, average="binary")
					recall = recall_score(test_labels, y_pred, average="binary")
					test_loss, _ = model.evaluate(test_sequences, test_labels, verbose=0)

					metrics = {"accuracy": acc, "precision": precision, "recall": recall, "loss": test_loss}
					export_ml_metrics(metrics, epoch_losses=history.history["loss"], training_time=training_time, learning_rate=learning_rate)

					# 🔹 авто‑логирование обучения
					from app.utils.metrics import log_training_run
					log_training_run(metrics, epoch_losses=history.history["loss"], training_time=training_time, learning_rate=learning_rate)

					return metrics
				else:
					raise ValueError("Недостаточно данных для GRU")

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
			logger.error(
				f"Ошибка сохранения эмбеддинга сигнала: {e}",
				extra={"operation": "insert", "collection": "signals"}
			)

		# 🔹 Авто‑логирование предсказания
		try:
			from app.utils.metrics import log_prediction
			log_prediction(features, result, confidence_score)
		except Exception as e:
			logger.error(f"Ошибка авто‑логирования предсказания: {e}")

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
			vector = self.embedding_model.encode(text).tolist()
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

		elif model_type == "pytorch_mlp":
			params = settings.MODEL_PARAMS
			input_size = len([
				"ema", "rsi", "macd", "hour", "atr",
				"bollinger_upper", "bollinger_lower", "bollinger",
				"obv", "stochastic", "vwap", "ichimoku",
				"volume", "volume_ma", "news_sentiment",
				"last_price", "spread", "liquidity_imbalance", "mark_price",
				"volatility", "momentum", "sentiment_ma", "bid_ask_ratio"
			])
			hidden_size = params.get("hidden_size", 64)
			dropout = params.get("dropout", 0.3)

			model = nn.Sequential(
				nn.Linear(input_size, hidden_size),
				nn.BatchNorm1d(hidden_size),
				nn.ReLU(),
				nn.Dropout(dropout),
				nn.Linear(hidden_size, hidden_size // 2),
				nn.ReLU(),
				nn.Linear(hidden_size // 2, 2)
			)
			model.load_state_dict(torch.load(path))
			self.model = model

		elif model_type == "pytorch_lstm":
			params = settings.MODEL_PARAMS
			input_size = len([
				"ema", "rsi", "macd", "hour", "atr",
				"bollinger_upper", "bollinger_lower", "bollinger",
				"obv", "stochastic", "vwap", "ichimoku",
				"volume", "volume_ma", "news_sentiment",
				"last_price", "spread", "liquidity_imbalance", "mark_price",
				"volatility", "momentum", "sentiment_ma", "bid_ask_ratio"
			])
			hidden_size = params.get("hidden_size", 64)
			num_layers = params.get("num_layers", 2)

			class LSTMModel(nn.Module):
				def __init__(self, input_size=input_size, hidden_size=hidden_size, num_layers=num_layers, output_size=2):
					super().__init__()
					self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
					self.fc = nn.Linear(hidden_size, output_size)

				def forward(self, x):
					out, _ = self.lstm(x)
					out = out[:, -1, :]
					return self.fc(out)

			model = LSTMModel()
			model.load_state_dict(torch.load(path))
			self.model = model

		elif model_type == "tensorflow_gru":
			self.model = keras.models.load_model(path)

		else:
			raise ValueError("Неизвестный тип модели")

		# Логирование загрузки
		log_model_load(model_type, path, settings.MODEL_PARAMS)


	async def load_model_from_db(self, name: str):
		"""Загрузить ML модель по имени из таблицы ml_models."""
		async with get_session() as session:
			ml_model = await crud.get_ml_model_by_name(session, name)
			if not ml_model:
				raise ValueError(f"Модель '{name}' не найдена в БД")

			# читаем параметры
			model_type = ml_model.type
			path = ml_model.path
			params = ml_model.params or {}

			# загружаем модель (без внутреннего логирования)
			self.load_model(path=path, model_type=model_type)

			# Логирование загрузки из БД — только один раз
			log_model_load(model_type, path, params)

			return ml_model


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
