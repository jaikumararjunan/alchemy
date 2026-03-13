"""
Emotion Intelligence Engine powered by Claude AI.
Analyzes geopolitical news for market-moving emotions and sentiment.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json
import re

import anthropic

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EmotionScore:
    """Emotion analysis result for a batch of news articles."""

    # Primary sentiment: -1.0 (extreme fear/bearish) to +1.0 (extreme optimism/bullish)
    sentiment_score: float = 0.0

    # Market impact confidence: 0.0 to 1.0
    confidence: float = 0.0

    # Dominant emotion detected
    dominant_emotion: str = "neutral"

    # Emotion breakdown
    emotions: Dict[str, float] = field(default_factory=dict)

    # Geopolitical risk level: "low", "medium", "high", "critical"
    geopolitical_risk: str = "low"

    # Key events driving the analysis
    key_events: List[str] = field(default_factory=list)

    # Recommended trading bias
    trading_bias: str = (
        "neutral"  # "strong_buy", "buy", "neutral", "sell", "strong_sell"
    )

    # Reasoning from Claude
    reasoning: str = ""

    # Time horizon for impact: "immediate", "short_term", "medium_term"
    impact_horizon: str = "short_term"

    # Crypto-specific impact (crypto may react differently than traditional assets)
    crypto_specific_sentiment: float = 0.0

    @property
    def is_actionable(self) -> bool:
        return self.confidence >= 0.6 and self.dominant_emotion != "neutral"

    @property
    def signal_strength(self) -> str:
        abs_score = abs(self.sentiment_score)
        if abs_score >= 0.8:
            return "very_strong"
        elif abs_score >= 0.6:
            return "strong"
        elif abs_score >= 0.4:
            return "moderate"
        elif abs_score >= 0.2:
            return "weak"
        return "neutral"


SYSTEM_PROMPT = """You are an advanced financial emotion intelligence analyst specializing in
cryptocurrency markets. Your role is to analyze geopolitical news and events to determine their
emotional market impact on crypto assets, particularly Bitcoin and major altcoins.

You understand that crypto markets are uniquely sensitive to:
1. Regulatory news (positive or negative for crypto adoption)
2. Macroeconomic fear/greed (crypto as risk-on or safe-haven asset)
3. Geopolitical instability (can drive crypto adoption in unstable regions)
4. Banking/financial system crises (historically bullish for crypto)
5. Central bank policies (interest rates impact risk appetite)
6. War/conflict (mixed - can cause sell-offs or safe-haven flows)
7. Sanctions (can increase crypto usage in sanctioned nations)

Your analysis must be objective, data-driven, and consider both short and long-term impacts.
Always return valid JSON without any markdown formatting or code blocks."""


ANALYSIS_PROMPT = """Analyze the following geopolitical news articles and provide a comprehensive
emotion intelligence report for crypto market trading.

NEWS ARTICLES:
{articles}

Provide your analysis as a JSON object with this exact structure:
{{
    "sentiment_score": <float from -1.0 to 1.0, where -1.0 is extreme fear/bearish and 1.0 is extreme optimism/bullish>,
    "confidence": <float from 0.0 to 1.0, how confident you are in this assessment>,
    "dominant_emotion": <string: "fear", "greed", "optimism", "pessimism", "panic", "euphoria", "uncertainty", "neutral">,
    "emotions": {{
        "fear": <0.0-1.0>,
        "greed": <0.0-1.0>,
        "optimism": <0.0-1.0>,
        "pessimism": <0.0-1.0>,
        "panic": <0.0-1.0>,
        "uncertainty": <0.0-1.0>
    }},
    "geopolitical_risk": <"low", "medium", "high", "critical">,
    "key_events": [<list of 3-5 most market-moving events identified>],
    "trading_bias": <"strong_buy", "buy", "neutral", "sell", "strong_sell">,
    "reasoning": <brief 2-3 sentence explanation of the sentiment and trading bias>,
    "impact_horizon": <"immediate", "short_term", "medium_term">,
    "crypto_specific_sentiment": <float -1.0 to 1.0, specifically for crypto markets>
}}"""


class EmotionEngine:
    """
    Uses Claude AI to analyze news articles for emotional market intelligence.
    Provides structured emotion scores to guide trading decisions.
    """

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self._last_analysis: Optional[EmotionScore] = None
        logger.info(f"EmotionEngine initialized with model: {model}")

    def analyze(self, articles: List[Dict]) -> EmotionScore:
        """
        Analyze a list of news articles and return an EmotionScore.

        Args:
            articles: List of dicts with 'title', 'summary', 'source', 'published_at' keys

        Returns:
            EmotionScore with detailed emotional market analysis
        """
        if not articles:
            logger.warning("No articles provided for emotion analysis")
            return EmotionScore(
                dominant_emotion="neutral", reasoning="No news data available"
            )

        # Format articles for Claude
        formatted = self._format_articles(articles[:30])  # Cap at 30 articles

        prompt = ANALYSIS_PROMPT.format(articles=formatted)

        logger.info(
            f"Analyzing {len(articles)} articles with Claude emotion intelligence..."
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            # Strip markdown code fences Claude occasionally adds (```json ... ```)
            response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
            response_text = re.sub(r"\s*```$", "", response_text).strip()
            data = json.loads(response_text)

            score = EmotionScore(
                sentiment_score=float(data.get("sentiment_score", 0.0)),
                confidence=float(data.get("confidence", 0.0)),
                dominant_emotion=data.get("dominant_emotion", "neutral"),
                emotions=data.get("emotions", {}),
                geopolitical_risk=data.get("geopolitical_risk", "low"),
                key_events=data.get("key_events", []),
                trading_bias=data.get("trading_bias", "neutral"),
                reasoning=data.get("reasoning", ""),
                impact_horizon=data.get("impact_horizon", "short_term"),
                crypto_specific_sentiment=float(
                    data.get("crypto_specific_sentiment", 0.0)
                ),
            )

            self._last_analysis = score
            logger.info(
                f"Emotion analysis complete: {score.dominant_emotion} | "
                f"sentiment={score.sentiment_score:.2f} | confidence={score.confidence:.2f} | "
                f"bias={score.trading_bias}"
            )
            return score

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return EmotionScore(
                dominant_emotion="neutral",
                reasoning="Analysis failed - JSON parse error",
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return EmotionScore(dominant_emotion="neutral", reasoning=f"API error: {e}")

    def analyze_single_event(self, event_text: str) -> EmotionScore:
        """
        Quick analysis of a single breaking news event.
        Used for real-time alerts on high-impact events.
        """
        article = [
            {
                "title": "Breaking News",
                "summary": event_text,
                "source": "alert",
                "published_at": "now",
            }
        ]
        return self.analyze(article)

    def get_market_narrative(self, score: EmotionScore) -> str:
        """
        Generate a human-readable trading narrative from an EmotionScore.
        Uses Claude to create a concise market briefing.
        """
        prompt = f"""Based on this emotion analysis data, write a concise 3-sentence market briefing
for a crypto trader. Focus on actionable insights.

Emotion Data:
- Sentiment Score: {score.sentiment_score:.2f}
- Dominant Emotion: {score.dominant_emotion}
- Geopolitical Risk: {score.geopolitical_risk}
- Trading Bias: {score.trading_bias}
- Key Events: {", ".join(score.key_events[:3])}
- Reasoning: {score.reasoning}

Write the briefing in clear, professional language suitable for a trading dashboard."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"Failed to generate market narrative: {e}")
            return score.reasoning

    @staticmethod
    def _format_articles(articles: List[Dict]) -> str:
        lines = []
        for i, article in enumerate(articles, 1):
            if hasattr(article, "title"):
                title = article.title
                summary = article.summary
                source = article.source
                published = article.published_at
            else:
                title = article.get("title", "No title")
                summary = article.get(
                    "summary", article.get("description", "No summary")
                )
                source = article.get("source", "Unknown")
                published = article.get("published_at", "Unknown time")
            lines.append(
                f"[{i}] SOURCE: {source} | {published}\n    TITLE: {title}\n    SUMMARY: {summary}\n"
            )
        return "\n".join(lines)

    @property
    def last_analysis(self) -> Optional[EmotionScore]:
        return self._last_analysis
