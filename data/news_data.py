# data/news_data.py

import warnings
warnings.filterwarnings('ignore')

import feedparser
import requests
from datetime import datetime, timedelta
import logging
import time

logger = logging.getLogger(__name__)


class IndianNewsFetcher:
    """
    Fetches Indian financial news from free RSS feeds.
    Economic Times, Moneycontrol, Business Standard.
    No API key needed.
    """

    def __init__(self):
        self.feeds = {
            'economic_times': (
                'https://economictimes.indiatimes.com/'
                'markets/rssfeeds/1977021501.cms'
            ),
            'moneycontrol': (
                'https://www.moneycontrol.com/rss/'
                'latestnews.xml'
            ),
            'business_standard': (
                'https://www.business-standard.com/'
                'rss/markets-106.rss'
            ),
        }
        self.cache = {}

    def fetch_for_symbol(self, symbol, days_back=3):
        """Fetch news for a specific stock."""

        clean = symbol.replace('.NS', '').replace(
            '.BO', ''
        )
        all_articles = []

        for source, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)

                for entry in feed.entries:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')

                    if clean.lower() in title.lower() or \
                       clean.lower() in summary.lower():

                        published = None
                        if hasattr(entry, 'published_parsed'):
                            if entry.published_parsed:
                                published = datetime(
                                    *entry.published_parsed[:6]
                                )

                        all_articles.append({
                            'title': title,
                            'summary': summary[:500],
                            'source': source,
                            'symbol': symbol,
                            'published': published,
                        })

                time.sleep(0.3)

            except Exception as e:
                logger.warning(
                    f"News error {source}: {e}"
                )

        self.cache[symbol] = all_articles
        return all_articles

    def fetch_market_news(self, days_back=1):
        """Fetch general market news."""

        all_articles = []

        for source, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)

                for entry in feed.entries[:20]:
                    all_articles.append({
                        'title': entry.get('title', ''),
                        'summary': entry.get(
                            'summary', ''
                        )[:500],
                        'source': source,
                        'symbol': 'MARKET',
                    })

                time.sleep(0.3)

            except Exception as e:
                logger.warning(
                    f"Market news error: {e}"
                )

        return all_articles

    def fetch_all(self, symbols):
        """Fetch news for multiple symbols."""

        print(
            f"\n📰 Fetching Indian news"
            f" for {len(symbols)} stocks..."
        )
        all_news = {}

        for i, symbol in enumerate(symbols):
            print(
                f"   [{i+1}/{len(symbols)}]"
                f" {symbol}...",
                end=" "
            )
            articles = self.fetch_for_symbol(symbol)
            all_news[symbol] = articles
            print(f"✅ {len(articles)} articles")
            time.sleep(0.5)

        return all_news