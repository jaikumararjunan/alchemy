"""
News fetcher for geopolitical and crypto market news.
Pulls from RSS feeds and NewsAPI.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional
from urllib.parse import urlencode

import feedparser
import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Article:
    title: str
    summary: str
    source: str
    url: str
    published_at: str
    relevance_score: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at,
            "relevance_score": self.relevance_score,
        }


class NewsFetcher:
    """
    Fetches geopolitical and crypto news from multiple sources.
    Scores each article for relevance to crypto market movement.
    """

    CRYPTO_BOOST_KEYWORDS = {
        "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
        "defi", "blockchain", "stablecoin", "sec", "cftc", "regulation",
        "exchange", "coinbase", "binance", "cbdc", "digital currency",
    }

    HIGH_IMPACT_KEYWORDS = {
        "war", "nuclear", "invasion", "coup", "crash", "crisis", "collapse",
        "sanction", "ban", "attack", "explosion", "emergency", "default",
        "recession", "depression", "hyperinflation", "bank run", "bankruptcy",
    }

    MEDIUM_IMPACT_KEYWORDS = {
        "inflation", "interest rate", "federal reserve", "fed", "rate hike",
        "rate cut", "gdp", "unemployment", "trade war", "tariff", "election",
        "geopolitical", "nato", "military", "conflict", "ceasefire", "peace",
        "opec", "oil", "energy", "currency", "dollar", "yuan", "ruble",
    }

    def __init__(self, news_api_key: str, rss_feeds: List[str],
                 keywords: List[str], max_articles: int = 50):
        self.news_api_key = news_api_key
        self.rss_feeds = rss_feeds
        self.keywords = [kw.lower() for kw in keywords]
        self.max_articles = max_articles
        self._cache: List[Article] = []
        self._last_fetch: float = 0.0

    def fetch(self, force: bool = False, max_age_minutes: int = 15) -> List[Article]:
        """
        Fetch fresh articles. Uses cache if recently fetched.
        Returns articles sorted by relevance score descending.
        """
        age = time.time() - self._last_fetch
        if not force and age < max_age_minutes * 60 and self._cache:
            logger.debug(f"Returning {len(self._cache)} cached articles (age={age:.0f}s)")
            return self._cache

        articles: List[Article] = []

        # Fetch from RSS feeds
        rss_articles = self._fetch_rss()
        articles.extend(rss_articles)
        logger.info(f"Fetched {len(rss_articles)} articles from RSS feeds")

        # Fetch from NewsAPI if key available
        if self.news_api_key:
            api_articles = self._fetch_newsapi()
            articles.extend(api_articles)
            logger.info(f"Fetched {len(api_articles)} articles from NewsAPI")

        # Score and deduplicate
        articles = self._deduplicate(articles)
        for article in articles:
            article.relevance_score = self._score_relevance(article)

        # Sort by relevance and limit
        articles.sort(key=lambda a: a.relevance_score, reverse=True)
        articles = articles[:self.max_articles]

        self._cache = articles
        self._last_fetch = time.time()
        logger.info(f"Total {len(articles)} relevant articles fetched and scored")
        return articles

    def fetch_breaking(self) -> List[Article]:
        """
        Fetch only the most recent, high-impact articles.
        Used for real-time monitoring.
        """
        all_articles = self.fetch()
        return [a for a in all_articles if a.relevance_score >= 0.7]

    def get_crypto_specific(self) -> List[Article]:
        """Get articles that directly mention crypto."""
        all_articles = self.fetch()
        return [
            a for a in all_articles
            if any(kw in (a.title + a.summary).lower() for kw in self.CRYPTO_BOOST_KEYWORDS)
        ]

    def _fetch_rss(self) -> List[Article]:
        articles = []
        for feed_url in self.rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    source = feed.feed.get("title", feed_url)
                    link = entry.get("link", "")
                    published = self._parse_date(entry)

                    # Filter by keywords
                    combined = (title + " " + summary).lower()
                    if any(kw in combined for kw in self.keywords):
                        articles.append(Article(
                            title=title,
                            summary=summary[:500],
                            source=source,
                            url=link,
                            published_at=published,
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed {feed_url}: {e}")
        return articles

    def _fetch_newsapi(self) -> List[Article]:
        articles = []
        query = " OR ".join(self.keywords[:10])
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 30,
            "apiKey": self.news_api_key,
        }
        url = f"https://newsapi.org/v2/everything?{urlencode(params)}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("articles", []):
                articles.append(Article(
                    title=item.get("title", ""),
                    summary=item.get("description", "")[:500],
                    source=item.get("source", {}).get("name", "NewsAPI"),
                    url=item.get("url", ""),
                    published_at=item.get("publishedAt", ""),
                ))
        except Exception as e:
            logger.warning(f"NewsAPI fetch failed: {e}")
        return articles

    def _score_relevance(self, article: Article) -> float:
        """
        Score article relevance to crypto markets (0.0 to 1.0).
        Considers keyword matches, source quality, recency.
        """
        score = 0.0
        combined = (article.title + " " + article.summary).lower()

        # Crypto direct mention bonus (+0.4)
        crypto_hits = sum(1 for kw in self.CRYPTO_BOOST_KEYWORDS if kw in combined)
        score += min(crypto_hits * 0.15, 0.4)

        # High-impact event bonus (+0.3)
        high_hits = sum(1 for kw in self.HIGH_IMPACT_KEYWORDS if kw in combined)
        score += min(high_hits * 0.15, 0.3)

        # Medium-impact keyword bonus (+0.2)
        med_hits = sum(1 for kw in self.MEDIUM_IMPACT_KEYWORDS if kw in combined)
        score += min(med_hits * 0.05, 0.2)

        # Base score for matching any tracked keyword (+0.1)
        if any(kw in combined for kw in self.keywords):
            score += 0.1

        return min(score, 1.0)

    @staticmethod
    def _parse_date(entry) -> str:
        if hasattr(entry, "published"):
            return str(entry.published)
        if hasattr(entry, "updated"):
            return str(entry.updated)
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _deduplicate(articles: List[Article]) -> List[Article]:
        seen_titles = set()
        unique = []
        for a in articles:
            title_key = a.title[:60].lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(a)
        return unique
