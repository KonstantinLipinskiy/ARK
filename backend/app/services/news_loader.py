# app/services/news_loader.py
import requests
import feedparser
from app.utils.logger import logger

class NewsLoader:
	def __init__(self, newsdata_api_key=None):
		self.api_key = newsdata_api_key

	def fetch_newsdata(self, query="bitcoin", language="en"):
		"""Загрузка новостей из NewsData.io по монете"""
		try:
			url = (
				f"https://newsdata.io/api/1/news?"
				f"apikey={self.api_key}&q={query}&language={language}&category=business"
			)
			resp = requests.get(url)
			if resp.status_code == 200:
				data = resp.json()
				results = []
				for article in data.get("results", []):
					results.append({
						"title": article.get("title"),
						"content": article.get("description", ""),
						"source": article.get("source_id", "newsdata.io"),
						"pubDate": article.get("pubDate")  # 🔹 унифицировано
					})
				return results
			return []
		except Exception as e:
			logger.error(
				f"❌ NewsData.io error: {e}",
				extra={"operation": "fetch_news", "collection": "newsdata"}
			)
			return []

	def fetch_coindesk_rss(self):
		"""Загрузка новостей из CoinDesk RSS"""
		try:
			rss_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
			feed = feedparser.parse(rss_url)
			results = []
			for entry in feed.entries:
				results.append({
					"title": getattr(entry, "title", None),
					"content": getattr(entry, "summary", ""),
					"source": "coindesk",
					"pubDate": getattr(entry, "published", None)  # 🔹 унифицировано
				})
			return results
		except Exception as e:
			logger.error(
				f"❌ CoinDesk RSS error: {e}",
				extra={"operation": "fetch_news", "collection": "coindesk"}
			)
			return []
