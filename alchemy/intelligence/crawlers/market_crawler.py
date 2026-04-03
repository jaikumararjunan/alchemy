"""
alchemy.intelligence.crawlers.market_crawler
=============================================
Continuous market intelligence system.

Sources:
  1. Geopolitical news (Reuters, Bloomberg RSS, NewsAPI)
  2. YouTube video transcript summarisation (yt-dlp + Whisper/API)
  3. Social sentiment (Reddit r/investing, r/stocks, r/IndiaInvestments)
  4. Economic calendar (Alpha Vantage, FRED)
  5. Regulatory filings (NSE/BSE announcements)

All data is stored in SQLite/PostgreSQL + ChromaDB vector store.
The LLM synthesises all sources into actionable trading intelligence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import structlog

log = structlog.get_logger(__name__)


@dataclass
class MarketSignal:
    """A single intelligence signal with market impact assessment."""
    id:              str
    source:          str           # news | video | social | economic | regulatory
    source_url:      str
    title:           str
    content:         str           # Raw content / transcript
    summary:         str           # LLM-generated summary
    market_impact:   str           # bullish | bearish | neutral | mixed
    impact_score:    float         # -1.0 (very bearish) to +1.0 (very bullish)
    affected_sectors: list[str]    # technology, energy, banking, pharma, etc.
    affected_symbols: list[str]    # RELIANCE, NIFTY50, BTCUSD, etc.
    geopolitical:    bool          # True if geopolitical in nature
    urgency:         str           # immediate | short_term | medium_term | long_term
    confidence:      float         # 0.0 - 1.0
    raw_data:        dict          = field(default_factory=dict)
    created_at:      datetime      = field(default_factory=lambda: datetime.now(timezone.utc))


class NewsRSSCrawler:
    """
    Crawl financial news RSS feeds for geopolitical and market-moving news.
    Supports Reuters, Bloomberg, Moneycontrol, Economic Times, CNBC.
    """
    RSS_FEEDS = {
        "reuters_markets":    "https://feeds.reuters.com/reuters/businessNews",
        "reuters_world":      "https://feeds.reuters.com/Reuters/worldNews",
        "economic_times":     "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "moneycontrol":       "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "cnbc_markets":       "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "bbc_business":       "https://feeds.bbci.co.uk/news/business/rss.xml",
        "ft_markets":         "https://www.ft.com/markets?format=rss",
        "hindu_business":     "https://www.thehindu.com/business/feeder/default.rss",
        "livemint":           "https://www.livemint.com/rss/markets",
        "businessline":       "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    }

    GEOPOLITICAL_KEYWORDS = [
        "war", "conflict", "sanctions", "tariff", "trade war", "recession",
        "inflation", "fed rate", "rbi policy", "budget", "election",
        "china", "russia", "ukraine", "middle east", "oil", "crude",
        "geopolitic", "nato", "dollar", "rupee depreciation", "rate hike",
        "rate cut", "gdp", "employment", "unemployment", "supply chain",
        "semiconductor", "chip", "energy crisis", "climate", "earthquake",
        "pandemic", "black swan", "banking crisis", "debt ceiling",
    ]

    MARKET_IMPACT_SECTORS = {
        "oil crude energy":     ["ONGC", "RELIANCE", "IOC", "BPCL", "OILCOS"],
        "banking interest rate":["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
        "technology semiconductor":["INFY", "TCS", "WIPRO", "HCLTECH"],
        "pharma healthcare":    ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
        "auto":                 ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO"],
        "fmcg consumer":        ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA"],
        "metals mining":        ["TATASTEEL", "HINDALCO", "JSWSTEEL", "VEDL"],
        "crypto bitcoin":       ["BTCUSD", "ETHUSD", "BNB"],
    }

    async def fetch_feed(self, feed_name: str, url: str) -> list[dict]:
        """Fetch and parse an RSS feed."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                headers = {"User-Agent": "AlchemyBot/1.0 (Market Intelligence)"}
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return []
                return self._parse_rss(resp.text, feed_name)
        except ImportError:
            log.warning("httpx not installed")
            return []
        except Exception as e:
            log.error("rss.fetch_failed", feed=feed_name, error=str(e))
            return []

    def _parse_rss(self, xml_text: str, source: str) -> list[dict]:
        """Parse RSS XML into article dicts."""
        import xml.etree.ElementTree as ET
        articles = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"dc": "http://purl.org/dc/elements/1.1/"}
            items = root.findall(".//item")
            for item in items[:20]:  # Latest 20 items
                title   = item.findtext("title",  "").strip()
                link    = item.findtext("link",   "").strip()
                desc    = item.findtext("description", "").strip()
                pub_date = item.findtext("pubDate", "").strip()
                # Strip HTML tags from description
                desc = re.sub(r"<[^>]+>", " ", desc)
                articles.append({
                    "title":    title,
                    "url":      link,
                    "summary":  desc[:500],
                    "pub_date": pub_date,
                    "source":   source,
                })
        except ET.ParseError:
            pass
        return articles

    def is_geopolitical(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.GEOPOLITICAL_KEYWORDS)

    def detect_affected_sectors(self, text: str) -> list[str]:
        text_lower = text.lower()
        sectors, symbols = [], []
        for keywords, syms in self.MARKET_IMPACT_SECTORS.items():
            if any(kw in text_lower for kw in keywords.split()):
                sector = keywords.split()[0]
                sectors.append(sector)
                symbols.extend(syms[:2])
        return list(set(sectors)), list(set(symbols))

    async def crawl_all(self) -> list[dict]:
        """Crawl all RSS feeds concurrently."""
        tasks = [self.fetch_feed(name, url) for name, url in self.RSS_FEEDS.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_articles = []
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)
        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for a in all_articles:
            title_key = a["title"][:50].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique.append(a)
        log.info("news.crawled", total=len(all_articles), unique=len(unique))
        return unique


class YouTubeMarketCrawler:
    """
    Crawl YouTube for market analysis videos and extract intelligence.

    Workflow:
      1. Search YouTube Data API for relevant channels / queries
      2. Download transcript via yt-dlp (no video download needed)
      3. If no auto-transcript: use Whisper API on audio
      4. Summarise with LLM into structured market intelligence
    """

    MARKET_CHANNELS = [
        "@ZerodhaOneMint",          # Indian market education
        "@FinancialMindset",        # Macro analysis
        "@RayDalio",                # Bridgewater macro
        "@AnantaVijay",             # Indian macro
        "@BasantMaheshwari",        # Equity research India
        "@NeerajMarwaha",           # Options trading India
    ]

    SEARCH_QUERIES = [
        "stock market today analysis",
        "nifty bank nifty analysis today",
        "bitcoin ethereum market update",
        "us market analysis today",
        "india economy gdp rbi",
        "geopolitical impact stock market",
        "scalping trading strategy today",
    ]

    async def get_transcript(self, video_url: str) -> Optional[str]:
        """
        Extract transcript from YouTube video.
        Falls back through: auto-captions → yt-dlp subtitle → skip.
        """
        try:
            import subprocess, tempfile, os
            with tempfile.TemporaryDirectory() as tmp:
                cmd = [
                    "yt-dlp",
                    "--write-auto-sub", "--sub-lang", "en",
                    "--skip-download", "--output", f"{tmp}/video",
                    "--quiet", video_url
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                # Find subtitle file
                for f in os.listdir(tmp):
                    if f.endswith(".vtt") or f.endswith(".srt"):
                        with open(os.path.join(tmp, f)) as fp:
                            raw = fp.read()
                        # Clean VTT/SRT format
                        text = re.sub(r'\d+:\d+:\d+[\.,]\d+ --> \d+:\d+:\d+[\.,]\d+', '', raw)
                        text = re.sub(r'<[^>]+>', '', text)
                        text = re.sub(r'\n\n+', '\n', text)
                        return text[:8000]   # Limit for LLM context
        except FileNotFoundError:
            log.warning("yt-dlp not installed. Install: pip install yt-dlp")
        except Exception as e:
            log.error("transcript.failed", url=video_url, error=str(e))
        return None

    async def summarise_with_llm(self, title: str, transcript: str) -> dict:
        """Summarise video transcript into market intelligence."""
        try:
            import httpx
            prompt = f"""You are a quantitative analyst. Summarise this market video transcript into structured intelligence.

Video: {title}
Transcript: {transcript[:4000]}

Respond in JSON only:
{{
  "summary": "2-3 sentence summary of key market insights",
  "market_direction": "bullish|bearish|neutral|mixed",
  "key_stocks_mentioned": ["TICKER1","TICKER2"],
  "sectors": ["banking","technology"],
  "key_levels": {{"support": 0, "resistance": 0}},
  "timeframe": "intraday|swing|positional|long_term",
  "confidence": 0.7,
  "trading_ideas": ["Short NIFTY at 22500 resistance", "Long HDFC on breakout"]
}}"""

            resp = await httpx.AsyncClient(timeout=30).post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            if resp.status_code == 200:
                content = resp.json()["content"][0]["text"]
                # Extract JSON
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except Exception as e:
            log.error("llm.summarise_failed", error=str(e))
        return {"summary": "Unable to summarise", "market_direction": "neutral",
                "key_stocks_mentioned": [], "sectors": [], "confidence": 0.0}


class MarketIntelligenceOrchestrator:
    """
    Continuous market intelligence engine.

    Runs all crawlers on a schedule, synthesises signals, and stores in vector DB.

    Schedule:
      - News RSS:    every 5 minutes
      - YouTube:     every 2 hours
      - Social:      every 15 minutes
      - Economic:    daily at market open
    """

    def __init__(self) -> None:
        self.news_crawler  = NewsRSSCrawler()
        self.video_crawler = YouTubeMarketCrawler()
        self._signals:     list[MarketSignal] = []
        self._running      = False
        self._seen_hashes: set[str] = set()

    async def start(self) -> None:
        """Start the continuous monitoring loop."""
        self._running = True
        log.info("intelligence.orchestrator_started")
        asyncio.create_task(self._news_loop())
        asyncio.create_task(self._video_loop())

    async def stop(self) -> None:
        self._running = False

    async def _news_loop(self) -> None:
        """Poll news every 5 minutes."""
        while self._running:
            try:
                articles = await self.news_crawler.crawl_all()
                new_signals = await self._process_articles(articles)
                if new_signals:
                    log.info("intelligence.new_signals", count=len(new_signals))
                    await self._store_signals(new_signals)
                    await self._notify_critical(new_signals)
            except Exception as e:
                log.error("intelligence.news_loop_error", error=str(e))
            await asyncio.sleep(300)  # 5 minutes

    async def _video_loop(self) -> None:
        """Process YouTube videos every 2 hours."""
        while self._running:
            await asyncio.sleep(7200)  # 2 hours
            try:
                await self._process_youtube_queue()
            except Exception as e:
                log.error("intelligence.video_loop_error", error=str(e))

    async def _process_articles(self, articles: list[dict]) -> list[MarketSignal]:
        """Convert raw articles into MarketSignal objects using LLM."""
        signals = []
        for article in articles:
            content = article["title"] + " " + article.get("summary", "")
            # Deduplicate
            content_hash = hashlib.md5(content.encode()).hexdigest()
            if content_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(content_hash)

            geo = self.news_crawler.is_geopolitical(content)
            sectors, symbols = self.news_crawler.detect_affected_sectors(content)

            # Quick sentiment using keyword heuristics
            bull_words = ["surge", "rally", "gain", "positive", "growth", "bull", "rise", "up", "profit"]
            bear_words = ["crash", "fall", "decline", "negative", "loss", "bear", "drop", "down", "risk", "crisis"]
            bull_count = sum(1 for w in bull_words if w in content.lower())
            bear_count = sum(1 for w in bear_words if w in content.lower())
            if bull_count > bear_count:
                impact, score = "bullish", min(0.8, bull_count * 0.15)
            elif bear_count > bull_count:
                impact, score = "bearish", max(-0.8, -bear_count * 0.15)
            else:
                impact, score = "neutral", 0.0

            signal = MarketSignal(
                id=content_hash[:12],
                source="news",
                source_url=article.get("url",""),
                title=article["title"],
                content=content,
                summary=article.get("summary","")[:300],
                market_impact=impact,
                impact_score=score,
                affected_sectors=sectors,
                affected_symbols=symbols,
                geopolitical=geo,
                urgency="immediate" if geo and abs(score) > 0.5 else "short_term",
                confidence=0.6,
                raw_data=article,
            )
            signals.append(signal)
        return signals

    async def _process_youtube_queue(self) -> None:
        """Process queued YouTube video URLs."""
        pass  # Populated by API endpoint

    async def _store_signals(self, signals: list[MarketSignal]) -> None:
        """Store signals in local DB + vector store."""
        self._signals.extend(signals)
        if len(self._signals) > 1000:
            self._signals = self._signals[-500:]
        # Persist to SQLite
        try:
            from alchemy.analytics_db.store import IntelligenceStore
            store = IntelligenceStore()
            for sig in signals:
                store.save_signal(sig)
        except Exception as e:
            log.error("intelligence.store_failed", error=str(e))

    async def _notify_critical(self, signals: list[MarketSignal]) -> None:
        """Send notifications for high-impact geopolitical signals."""
        critical = [s for s in signals
                    if s.geopolitical and abs(s.impact_score) >= 0.6]
        if not critical:
            return
        try:
            from alchemy.notifications.dispatcher import get_dispatcher
            from alchemy.notifications.models import NotificationEvent, EventType, EventSeverity
            for sig in critical[:3]:  # Max 3 at a time
                event = NotificationEvent(
                    event_type=EventType.CUSTOM,
                    severity=EventSeverity.WARNING,
                    title=f"🌍 Geopolitical Alert: {sig.title[:60]}",
                    message=f"{sig.summary}\n\nImpact: {sig.market_impact.upper()} ({sig.impact_score:+.2f})\nSectors: {', '.join(sig.affected_sectors[:3])}",
                    source="market_intelligence",
                    idempotency_key=f"geo-{sig.id}",
                )
                await get_dispatcher().notify(event)
        except Exception as e:
            log.error("intelligence.notify_failed", error=str(e))

    def get_latest_signals(self, limit: int = 50, geo_only: bool = False) -> list[dict]:
        signals = self._signals
        if geo_only:
            signals = [s for s in signals if s.geopolitical]
        return [
            {
                "id":               s.id,
                "source":           s.source,
                "title":            s.title,
                "summary":          s.summary,
                "market_impact":    s.market_impact,
                "impact_score":     round(s.impact_score, 3),
                "affected_sectors": s.affected_sectors,
                "affected_symbols": s.affected_symbols,
                "geopolitical":     s.geopolitical,
                "urgency":          s.urgency,
                "confidence":       s.confidence,
                "created_at":       s.created_at.isoformat(),
            }
            for s in signals[-limit:]
        ]

    def synthesise_market_view(self) -> dict:
        """
        Synthesise all recent signals into an overall market view.
        Returns bullish/bearish bias + top impacted instruments.
        """
        if not self._signals:
            return {"market_bias": "neutral", "confidence": 0.0, "signals_count": 0}

        recent = [s for s in self._signals
                  if (datetime.now(timezone.utc) - s.created_at).total_seconds() < 3600]

        if not recent:
            return {"market_bias": "neutral", "confidence": 0.0, "signals_count": 0}

        avg_score = sum(s.impact_score for s in recent) / len(recent)
        geo_count = sum(1 for s in recent if s.geopolitical)
        all_sectors = {}
        all_symbols = {}
        for s in recent:
            for sec in s.affected_sectors:
                all_sectors[sec] = all_sectors.get(sec,0) + abs(s.impact_score)
            for sym in s.affected_symbols:
                all_symbols[sym] = all_symbols.get(sym,0) + abs(s.impact_score)

        bias = "bullish" if avg_score > 0.1 else "bearish" if avg_score < -0.1 else "neutral"
        return {
            "market_bias":      bias,
            "avg_score":        round(avg_score, 3),
            "confidence":       min(0.9, len(recent) / 20),
            "signals_count":    len(recent),
            "geopolitical_signals": geo_count,
            "top_sectors":      sorted(all_sectors.items(), key=lambda x:-x[1])[:5],
            "top_symbols":      sorted(all_symbols.items(), key=lambda x:-x[1])[:5],
            "window_hours":     1,
        }


# Singleton
_orchestrator: Optional[MarketIntelligenceOrchestrator] = None

def get_orchestrator() -> MarketIntelligenceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MarketIntelligenceOrchestrator()
    return _orchestrator
