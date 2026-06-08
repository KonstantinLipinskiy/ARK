import requests
import feedparser
from app.utils.logger import logger

class NewsLoader:
	def __init__(self, newsdata_api_key=None):
		self.api_key = newsdata_api_key

	def fetch_newsdata(self, query="bitcoin", language="en"):
		"""Загрузка новостей из NewsData.io по монете"""
		try:
			url = f"https://newsdata.io/api/1/news?apikey={self.api_key}&q={query}&language={language}&category=business"
			resp = requests.get(url)
			if resp.status_code == 200:
				data = resp.json()
				return [article["title"] for article in data.get("results", [])]
			return []
		except Exception as e:
			logger.error(f"❌ NewsData.io error: {e}")
			return []

	def fetch_coindesk_rss(self):
		"""Загрузка новостей из CoinDesk RSS"""
		try:
			rss_url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
			feed = feedparser.parse(rss_url)
			return [entry.title for entry in feed.entries]
		except Exception as e:
			logger.error(f"❌ CoinDesk RSS error: {e}")
			return []
