"""
Geopolitical Analyzer - categorizes and scores geopolitical events
for their expected impact on crypto markets.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from src.intelligence.news_fetcher import Article
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GeopoliticalEvent:
    """A categorized geopolitical event with market impact scoring."""
    category: str          # e.g. "war", "sanctions", "regulation", "macro"
    severity: str          # "low", "medium", "high", "critical"
    region: str            # Affected region
    description: str
    articles: List[Article] = field(default_factory=list)
    crypto_impact_score: float = 0.0    # -1.0 to 1.0
    confidence: float = 0.0
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Impact rules: (keywords, base_impact, description)
# Positive impact = bullish for crypto
# Negative impact = bearish for crypto
GEOPOLITICAL_IMPACT_RULES: List[Tuple[List[str], float, str]] = [
    # Regulatory - negative for crypto
    (["ban", "outlaw", "prohibit", "illegal", "crackdown", "arrest", "seized"], -0.7, "Crypto regulatory crackdown"),
    (["sec", "lawsuit", "enforcement", "violation", "fraud"], -0.5, "Regulatory enforcement action"),
    (["regulate", "regulation", "framework", "compliance", "clarity"], 0.2, "Crypto regulatory clarity"),
    (["etf approved", "etf approval", "spot bitcoin etf"], 0.8, "Crypto ETF approval"),
    (["cbdc", "central bank digital", "digital currency"], -0.3, "CBDC development (competition)"),

    # Banking/Financial crisis - bullish for crypto
    (["bank run", "bank collapse", "banking crisis", "bank failure"], 0.7, "Banking system stress"),
    (["inflation", "hyperinflation", "currency crisis", "currency collapse"], 0.6, "Currency devaluation risk"),
    (["debt crisis", "sovereign debt", "default", "imf bailout"], 0.5, "Sovereign debt crisis"),
    (["recession", "economic crisis", "depression"], -0.2, "Economic slowdown (risk-off)"),

    # War/Conflict - mixed
    (["nuclear", "nuclear war", "nuclear threat"], -0.8, "Nuclear threat (extreme risk-off)"),
    (["invasion", "war declared", "military offensive"], -0.5, "Military conflict escalation"),
    (["ceasefire", "peace deal", "peace talks", "de-escalation"], 0.3, "Conflict de-escalation"),
    (["sanction", "sanctions"], 0.2, "Sanctions (drive crypto adoption)"),

    # Macro - interest rates
    (["rate hike", "interest rate increase", "tightening"], -0.4, "Interest rate increase"),
    (["rate cut", "interest rate cut", "easing", "quantitative easing", "qe"], 0.5, "Monetary easing"),
    (["pivot", "fed pivot", "dovish"], 0.4, "Dovish monetary policy shift"),
    (["hawkish", "taper", "tapering"], -0.3, "Hawkish monetary policy"),

    # Geopolitical instability - often bullish for crypto as alternative asset
    (["coup", "political instability", "civil unrest", "protest"], 0.2, "Political instability"),
    (["capital controls", "capital control"], 0.5, "Capital controls (drive crypto adoption)"),
    (["currency devaluation", "devalue", "depreciation"], 0.4, "Currency devaluation"),

    # Institutional adoption - bullish
    (["institutional", "institutional buying", "corporate treasury", "nation-state"], 0.6, "Institutional adoption"),
    (["legal tender", "bitcoin legal tender"], 0.7, "Bitcoin as legal tender"),
]

REGION_KEYWORDS = {
    "USA": ["us", "america", "united states", "washington", "congress", "senate", "white house"],
    "China": ["china", "beijing", "chinese", "prc", "xi jinping"],
    "Russia": ["russia", "moscow", "russian", "putin", "kremlin"],
    "Europe": ["europe", "eu", "european", "ecb", "eurozone", "germany", "france"],
    "Middle East": ["middle east", "israel", "iran", "saudi", "opec", "gulf", "iran"],
    "Asia": ["japan", "korea", "india", "southeast asia", "asean"],
    "Global": ["global", "worldwide", "international", "imf", "world bank", "united nations"],
}


class GeopoliticalAnalyzer:
    """
    Analyzes news articles to identify geopolitical events and
    estimate their potential impact on crypto markets.
    """

    def __init__(self):
        logger.info("GeopoliticalAnalyzer initialized")

    def analyze(self, articles: List[Article]) -> List[GeopoliticalEvent]:
        """
        Analyze articles to extract and categorize geopolitical events.
        Returns a list of events sorted by impact magnitude.
        """
        events: List[GeopoliticalEvent] = []

        for article in articles:
            combined = (article.title + " " + article.summary).lower()
            matched_events = self._match_rules(combined)

            for category, impact, description in matched_events:
                region = self._detect_region(combined)
                severity = self._impact_to_severity(abs(impact))

                # Check if we already have a similar event
                existing = self._find_similar_event(events, category, description)
                if existing:
                    existing.articles.append(article)
                    # Increase confidence with more articles confirming the event
                    existing.confidence = min(existing.confidence + 0.1, 1.0)
                else:
                    events.append(GeopoliticalEvent(
                        category=category,
                        severity=severity,
                        region=region,
                        description=description,
                        articles=[article],
                        crypto_impact_score=impact,
                        confidence=0.5 + (article.relevance_score * 0.3),
                    ))

        # Sort by impact magnitude
        events.sort(key=lambda e: abs(e.crypto_impact_score) * e.confidence, reverse=True)
        logger.info(f"Detected {len(events)} geopolitical events from {len(articles)} articles")
        return events

    def get_aggregate_impact(self, events: List[GeopoliticalEvent]) -> Dict:
        """
        Aggregate all events into a single market impact assessment.
        """
        if not events:
            return {
                "total_impact": 0.0,
                "bullish_pressure": 0.0,
                "bearish_pressure": 0.0,
                "net_sentiment": "neutral",
                "dominant_events": [],
                "risk_level": "low",
            }

        weighted_impacts = []
        bullish_pressure = 0.0
        bearish_pressure = 0.0

        for event in events:
            weighted = event.crypto_impact_score * event.confidence
            weighted_impacts.append(weighted)
            if weighted > 0:
                bullish_pressure += weighted
            else:
                bearish_pressure += abs(weighted)

        total_impact = sum(weighted_impacts) / max(len(weighted_impacts), 1)
        total_impact = max(-1.0, min(1.0, total_impact))

        # Determine net sentiment
        if total_impact >= 0.5:
            net_sentiment = "strongly_bullish"
        elif total_impact >= 0.2:
            net_sentiment = "bullish"
        elif total_impact <= -0.5:
            net_sentiment = "strongly_bearish"
        elif total_impact <= -0.2:
            net_sentiment = "bearish"
        else:
            net_sentiment = "neutral"

        # Determine risk level from event severities
        critical_count = sum(1 for e in events if e.severity == "critical")
        high_count = sum(1 for e in events if e.severity == "high")

        if critical_count >= 1:
            risk_level = "critical"
        elif high_count >= 2:
            risk_level = "high"
        elif high_count >= 1:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Top 3 dominant events
        dominant = [
            {"description": e.description, "impact": e.crypto_impact_score, "region": e.region}
            for e in events[:3]
        ]

        return {
            "total_impact": total_impact,
            "bullish_pressure": bullish_pressure,
            "bearish_pressure": bearish_pressure,
            "net_sentiment": net_sentiment,
            "dominant_events": dominant,
            "risk_level": risk_level,
            "event_count": len(events),
        }

    def get_risk_adjusted_signal(self, geo_impact: Dict, emotion_score) -> Optional[str]:
        """
        Combine geopolitical impact with emotion score to produce a final signal.
        Returns: "strong_buy", "buy", "neutral", "sell", "strong_sell", or None (no signal)
        """
        geo_signal = geo_impact["total_impact"]
        emotion_signal = emotion_score.crypto_specific_sentiment
        confidence = emotion_score.confidence
        risk_level = geo_impact["risk_level"]

        # Combine signals (weighted: 40% geo, 60% emotion/Claude analysis)
        combined = (geo_signal * 0.4) + (emotion_signal * 0.6)

        # Risk adjustment: reduce position size in high-risk environments
        if risk_level == "critical":
            combined *= 0.3  # Drastically reduce in extreme uncertainty
        elif risk_level == "high":
            combined *= 0.6
        elif risk_level == "medium":
            combined *= 0.8

        # Only signal if confidence is sufficient
        if confidence < 0.5:
            return "neutral"

        if combined >= 0.7:
            return "strong_buy"
        elif combined >= 0.3:
            return "buy"
        elif combined <= -0.7:
            return "strong_sell"
        elif combined <= -0.3:
            return "sell"
        return "neutral"

    @staticmethod
    def _match_rules(text: str) -> List[Tuple[str, float, str]]:
        matches = []
        for keywords, impact, description in GEOPOLITICAL_IMPACT_RULES:
            if any(kw in text for kw in keywords):
                category = description.split("(")[0].strip().lower().replace(" ", "_")
                matches.append((category, impact, description))
        return matches

    @staticmethod
    def _detect_region(text: str) -> str:
        for region, keywords in REGION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return region
        return "Global"

    @staticmethod
    def _impact_to_severity(abs_impact: float) -> str:
        if abs_impact >= 0.7:
            return "critical"
        elif abs_impact >= 0.5:
            return "high"
        elif abs_impact >= 0.3:
            return "medium"
        return "low"

    @staticmethod
    def _find_similar_event(events: List[GeopoliticalEvent],
                            category: str, description: str) -> Optional[GeopoliticalEvent]:
        for event in events:
            if event.category == category and event.description == description:
                return event
        return None
