"""Core emotion analyzer — alternate Claude emotion engine v2."""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import anthropic

from config import ClaudeConfig
from src.engine.models import Article, EmotionBreakdown, EmotionResult
from src.engine.prompts import ANALYSIS_PROMPT, NARRATIVE_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_SIGNAL_THRESHOLDS = [
    (0.7, "very_strong"),
    (0.4, "strong"),
    (0.2, "moderate"),
    (0.05, "weak"),
]


def _signal_strength(score: float) -> str:
    mag = abs(score)
    for threshold, label in _SIGNAL_THRESHOLDS:
        if mag >= threshold:
            return label
    return "neutral"


def _neutral_result(model: str, n: int, reason: str) -> EmotionResult:
    return EmotionResult(
        sentiment_score=0.0,
        confidence=0.0,
        dominant_emotion="neutral",
        emotions=EmotionBreakdown(),
        geopolitical_risk="low",
        key_events=[],
        trading_bias="neutral",
        reasoning=reason,
        impact_horizon="short_term",
        crypto_specific_sentiment=0.0,
        signal_strength="neutral",
        model_used=model,
        articles_analyzed=n,
    )


class EmotionAnalyzer:
    """Alternate Claude-powered emotion engine with multi-model support and narrative generation."""

    def __init__(self, cfg: ClaudeConfig) -> None:
        self._cfg = cfg
        self._client = anthropic.Anthropic(api_key=cfg.api_key)
        self._last_result: Optional[EmotionResult] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        articles: List[Article],
        model_override: Optional[str] = None,
        context: Optional[str] = None,
    ) -> EmotionResult:
        """Analyse a list of articles and return an EmotionResult."""
        if not articles:
            return _neutral_result(self._cfg.model, 0, "No articles provided.")

        model = model_override or self._cfg.model
        capped = articles[:30]

        context_block = f"\nADDITIONAL CONTEXT: {context}\n" if context else ""
        articles_text = "\n".join(
            f"{i+1}. SOURCE: {a.source}\n   TITLE: {a.title}\n   SUMMARY: {a.summary[:500]}"
            for i, a in enumerate(capped)
        )

        prompt = ANALYSIS_PROMPT.format(
            n=len(capped),
            context_block=context_block,
            articles=articles_text,
        )

        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=self._cfg.max_tokens,
                temperature=self._cfg.temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            return _neutral_result(model, len(capped), f"API error: {exc}")

        raw = message.content[0].text.strip()
        # Strip markdown fences if Claude adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error: %s | raw=%s", exc, raw[:200])
            return _neutral_result(model, len(capped), "JSON parse error from Claude.")

        emotions_data = data.get("emotions", {})
        result = EmotionResult(
            sentiment_score=float(data.get("sentiment_score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            dominant_emotion=data.get("dominant_emotion", "neutral"),
            emotions=EmotionBreakdown(
                fear=float(emotions_data.get("fear", 0.0)),
                greed=float(emotions_data.get("greed", 0.0)),
                optimism=float(emotions_data.get("optimism", 0.0)),
                pessimism=float(emotions_data.get("pessimism", 0.0)),
                panic=float(emotions_data.get("panic", 0.0)),
                uncertainty=float(emotions_data.get("uncertainty", 0.0)),
            ),
            geopolitical_risk=data.get("geopolitical_risk", "low"),
            key_events=data.get("key_events", []),
            trading_bias=data.get("trading_bias", "neutral"),
            reasoning=data.get("reasoning", ""),
            impact_horizon=data.get("impact_horizon", "short_term"),
            crypto_specific_sentiment=float(data.get("crypto_specific_sentiment", 0.0)),
            signal_strength=_signal_strength(float(data.get("sentiment_score", 0.0))),
            model_used=model,
            articles_analyzed=len(capped),
        )

        result.market_narrative = self._generate_narrative(result, model)
        self._last_result = result
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_narrative(self, result: EmotionResult, model: str) -> str:
        prompt = NARRATIVE_PROMPT.format(
            sentiment_score=result.sentiment_score,
            dominant_emotion=result.dominant_emotion,
            trading_bias=result.trading_bias,
            geopolitical_risk=result.geopolitical_risk,
            key_events=", ".join(result.key_events),
            reasoning=result.reasoning,
        )
        try:
            msg = self._client.messages.create(
                model=model,
                max_tokens=256,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as exc:
            logger.warning("Narrative generation failed: %s", exc)
            return result.reasoning

    @property
    def last_result(self) -> Optional[EmotionResult]:
        return self._last_result
