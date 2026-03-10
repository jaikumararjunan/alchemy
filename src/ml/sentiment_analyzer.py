"""
Sentiment Analyzer
==================
Fast, self-contained NLP sentiment model for crypto news headlines.

Two-stage pipeline:
  Stage 1 – Crypto-domain lexicon  : rule-based fast pass using a handcrafted
             crypto-specific word list with signed sentiment weights.
             Works immediately, zero training needed.
  Stage 2 – TF-IDF + Naive Bayes   : trained on labelled headlines from the
             emotion engine's history.  Provides a probability distribution
             over [very_negative, negative, neutral, positive, very_positive].

Output: SentimentAnalysis dataclass with score (-1 to +1), label, confidence,
        and top keywords that drove the decision.
"""
import re
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Crypto-domain lexicon (score: -2 to +2) ──────────────────────────────────

CRYPTO_LEXICON: Dict[str, float] = {
    # Strongly bullish
    "rally": 1.5, "surge": 1.5, "breakout": 1.4, "soar": 1.5,
    "all-time high": 2.0, "ath": 2.0, "bull": 1.3, "bullish": 1.5,
    "adoption": 1.2, "etf approved": 2.0, "etf": 1.2, "halving": 1.3,
    "institutional": 1.1, "accumulation": 1.0, "buy": 0.8,
    "partnership": 0.9, "upgrade": 0.8, "growth": 0.8, "gain": 0.7,
    "mainstream": 0.8, "legal tender": 1.5, "approve": 0.9,
    "recovery": 0.8, "rebound": 0.9, "moon": 1.2, "oversold": 0.7,
    # Mildly bullish
    "positive": 0.5, "optimism": 0.6, "confidence": 0.4, "support": 0.3,
    "stable": 0.2, "hodl": 0.5,
    # Mildly bearish
    "concern": -0.4, "uncertainty": -0.5, "volatile": -0.4, "slowdown": -0.4,
    "correction": -0.5, "pullback": -0.4, "overbought": -0.6,
    # Strongly bearish
    "crash": -1.8, "collapse": -1.8, "ban": -1.5, "hack": -1.6,
    "stolen": -1.7, "fraud": -1.8, "scam": -1.8, "rug pull": -2.0,
    "bear": -1.2, "bearish": -1.4, "sell-off": -1.4, "dump": -1.3,
    "regulation crackdown": -1.5, "lawsuit": -1.3, "fine": -1.0,
    "bankruptcy": -2.0, "insolvency": -1.9, "investigation": -1.2,
    "seizure": -1.5, "sanction": -1.4, "exploit": -1.6,
    "vulnerability": -1.3, "delisted": -1.5, "liquidated": -1.2,
    "plunge": -1.6, "tumble": -1.4, "tank": -1.5, "plummet": -1.7,
    # Geopolitical
    "war": -1.2, "conflict": -1.0, "inflation": -0.8, "recession": -1.1,
    "fed rate": -0.5, "interest rate hike": -0.9, "cbdc": -0.3,
    "sanctions": -1.2, "energy crisis": -0.8, "nuclear": -1.3,
    "ceasefire": 0.6, "peace": 0.5, "trade deal": 0.6,
}

NEGATION_WORDS = {"not", "no", "never", "without", "isn't", "aren't",
                  "wasn't", "won't", "don't", "doesn't", "didn't",
                  "cannot", "can't", "neither", "nor"}

INTENSIFIERS = {"very": 1.5, "highly": 1.4, "extremely": 1.8, "massively": 1.6,
                "slightly": 0.6, "somewhat": 0.7, "major": 1.3, "significant": 1.2}


@dataclass
class SentimentAnalysis:
    text: str = ""
    score: float = 0.0              # -1.0 to +1.0
    label: str = "neutral"          # very_negative | negative | neutral | positive | very_positive
    confidence: float = 0.5         # 0.0 to 1.0
    lexicon_score: float = 0.0      # raw lexicon contribution
    ml_score: float = 0.0           # ML model contribution
    top_keywords: List[str] = field(default_factory=list)
    is_crypto_relevant: bool = True

    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 4),
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "lexicon_score": round(self.lexicon_score, 4),
            "ml_score": round(self.ml_score, 4),
            "top_keywords": self.top_keywords[:5],
            "is_crypto_relevant": self.is_crypto_relevant,
        }


class SentimentAnalyzer:
    """
    Crypto-aware sentiment analyzer.

    Usage:
        analyzer = SentimentAnalyzer()
        result   = analyzer.analyze("Bitcoin ETF approved by SEC, price surges")
        results  = analyzer.analyze_batch(list_of_headlines)
        score    = analyzer.aggregate(results)  # single portfolio score
    """

    MIN_TRAIN_SAMPLES = 30

    def __init__(self):
        self._tfidf_vocab: Dict[str, int] = {}
        self._nb_log_priors: np.ndarray = np.zeros(5)
        self._nb_log_likelihoods: Optional[np.ndarray] = None   # (5, vocab)
        self._is_trained = False
        self._train_samples = 0
        self._label_map = {
            "very_negative": 0, "negative": 1, "neutral": 2,
            "positive": 3, "very_positive": 4,
        }
        self._rev_label = {v: k for k, v in self._label_map.items()}
        logger.info("SentimentAnalyzer initialised (lexicon: %d terms)", len(CRYPTO_LEXICON))

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, text: str) -> SentimentAnalysis:
        """Analyze a single piece of text."""
        if not text or not text.strip():
            return SentimentAnalysis()

        tokens = self._tokenize(text)

        # Stage 1: Lexicon
        lex_score, keywords = self._lexicon_score(tokens)
        lex_norm = max(-1.0, min(1.0, lex_score / 3.0))

        # Stage 2: ML (if trained)
        ml_score = 0.0
        ml_conf  = 0.5
        if self._is_trained:
            ml_probs = self._nb_predict(tokens)
            # Convert 5-class probabilities to -1..+1 score
            weights = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
            ml_score = float(np.dot(ml_probs, weights))
            ml_conf  = float(np.max(ml_probs))

        # Blend
        if self._is_trained:
            blended = lex_norm * 0.40 + ml_score * 0.60
            conf    = 0.4 + ml_conf * 0.6
        else:
            blended = lex_norm
            conf    = min(0.5 + abs(lex_norm) * 0.5, 0.9)

        label = self._score_to_label(blended)
        relevant = self._is_relevant(tokens)

        return SentimentAnalysis(
            text=text[:200],
            score=round(blended, 4),
            label=label,
            confidence=round(conf, 4),
            lexicon_score=round(lex_norm, 4),
            ml_score=round(ml_score, 4),
            top_keywords=keywords[:5],
            is_crypto_relevant=relevant,
        )

    def analyze_batch(self, texts: List[str]) -> List[SentimentAnalysis]:
        return [self.analyze(t) for t in texts]

    def aggregate(
        self,
        results: List[SentimentAnalysis],
        weight_by_relevance: bool = True,
    ) -> Dict:
        """Aggregate a list of analyses into portfolio-level signal."""
        if not results:
            return {"score": 0.0, "label": "neutral", "confidence": 0.5, "n": 0}

        scores  = np.array([r.score for r in results])
        weights = np.array([
            (1.5 if r.is_crypto_relevant else 0.5) * r.confidence
            for r in results
        ]) if weight_by_relevance else np.ones(len(results))

        total_w = weights.sum()
        if total_w == 0:
            return {"score": 0.0, "label": "neutral", "confidence": 0.5, "n": len(results)}

        w_score = float(np.dot(scores, weights) / total_w)
        avg_conf = float(np.mean([r.confidence for r in results]))
        label_counts: Dict[str, int] = defaultdict(int)
        for r in results:
            label_counts[r.label] += 1

        return {
            "score": round(w_score, 4),
            "label": self._score_to_label(w_score),
            "confidence": round(avg_conf, 4),
            "n": len(results),
            "label_distribution": dict(label_counts),
            "bullish_pct": round(sum(1 for r in results if r.score > 0.1) / len(results) * 100, 1),
            "bearish_pct": round(sum(1 for r in results if r.score < -0.1) / len(results) * 100, 1),
        }

    def train(self, texts: List[str], labels: List[str]) -> Dict:
        """
        Train the Naive Bayes stage on labelled headline data.
        labels should be: "very_negative" | "negative" | "neutral" |
                          "positive" | "very_positive"
        """
        if len(texts) < self.MIN_TRAIN_SAMPLES:
            return {"status": "insufficient_data", "n": len(texts)}

        # Build vocabulary
        all_tokens = [self._tokenize(t) for t in texts]
        vocab: Dict[str, int] = {}
        for toks in all_tokens:
            for tok in toks:
                if tok not in vocab:
                    vocab[tok] = len(vocab)
        self._tfidf_vocab = vocab
        V = len(vocab)

        # Count word occurrences per class (Multinomial NB with Laplace smoothing)
        n_classes = 5
        counts   = np.ones((n_classes, V))    # Laplace smoothing
        class_n  = np.zeros(n_classes)

        for toks, lbl in zip(all_tokens, labels):
            c = self._label_map.get(lbl, 2)
            class_n[c] += 1
            for tok in toks:
                if tok in vocab:
                    counts[c, vocab[tok]] += 1

        # Log-likelihoods
        row_sums = counts.sum(axis=1, keepdims=True)
        self._nb_log_likelihoods = np.log(counts / row_sums)

        # Priors
        total = class_n.sum()
        self._nb_log_priors = np.log((class_n + 1) / (total + n_classes))

        self._is_trained    = True
        self._train_samples = len(texts)
        logger.info("SentimentAnalyzer trained: %d samples, vocab=%d", len(texts), V)
        return {
            "status": "trained",
            "samples": len(texts),
            "vocab_size": V,
            "class_distribution": {self._rev_label[i]: int(class_n[i]) for i in range(n_classes)},
        }

    def auto_train_from_emotion_history(self, history: List[Dict]) -> Dict:
        """
        Bootstrap training from emotion engine history.
        Each entry should have 'reasoning' and 'trading_bias' or 'sentiment_score'.
        """
        texts, labels = [], []
        for h in history:
            text = h.get("reasoning", "") or h.get("text", "")
            if not text:
                continue
            score = h.get("sentiment_score", 0)
            if score > 0.5:
                lbl = "very_positive"
            elif score > 0.1:
                lbl = "positive"
            elif score < -0.5:
                lbl = "very_negative"
            elif score < -0.1:
                lbl = "negative"
            else:
                lbl = "neutral"
            texts.append(text)
            labels.append(lbl)
        return self.train(texts, labels)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        text = text.lower()
        # Keep multi-word phrases from lexicon
        for phrase in ["all-time high", "rug pull", "etf approved",
                       "regulation crackdown", "interest rate hike",
                       "legal tender", "trade deal", "fed rate"]:
            text = text.replace(phrase, phrase.replace(" ", "_"))
        words = re.findall(r"[a-z0-9_-]+", text)
        return words

    def _lexicon_score(self, tokens: List[str]) -> Tuple[float, List[str]]:
        score    = 0.0
        keywords = []
        negate   = False
        intensity = 1.0

        # Also check bigrams for compound terms
        bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
        all_terms = tokens + bigrams

        for i, tok in enumerate(tokens):
            if tok in NEGATION_WORDS:
                negate = True
                continue
            if tok in INTENSIFIERS:
                intensity = INTENSIFIERS[tok]
                continue

            word_score = CRYPTO_LEXICON.get(tok, 0.0)
            # check bigram
            if i < len(tokens) - 1:
                bi = f"{tok}_{tokens[i+1]}"
                word_score = max(word_score, CRYPTO_LEXICON.get(bi, 0.0), key=abs)

            if word_score != 0.0:
                effective = word_score * intensity * (-1 if negate else 1)
                score += effective
                keywords.append(f"{tok}({effective:+.1f})")
                intensity = 1.0
                negate = False

        # Decay negation after 3 tokens
        return score, keywords

    def _nb_predict(self, tokens: List[str]) -> np.ndarray:
        if self._nb_log_likelihoods is None:
            return np.ones(5) / 5
        log_probs = self._nb_log_priors.copy()
        for tok in tokens:
            if tok in self._tfidf_vocab:
                log_probs += self._nb_log_likelihoods[:, self._tfidf_vocab[tok]]
        # Softmax
        log_probs -= log_probs.max()
        probs = np.exp(log_probs)
        return probs / probs.sum()

    @staticmethod
    def _score_to_label(score: float) -> str:
        if score >= 0.6:
            return "very_positive"
        if score >= 0.15:
            return "positive"
        if score <= -0.6:
            return "very_negative"
        if score <= -0.15:
            return "negative"
        return "neutral"

    @staticmethod
    def _is_relevant(tokens: List[str]) -> bool:
        crypto_terms = {
            "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain",
            "defi", "nft", "altcoin", "token", "exchange", "binance",
            "coinbase", "solana", "polygon", "ripple", "xrp", "stablecoin",
            "usdt", "usdc", "web3", "dao", "mining", "wallet", "halving",
            "perpetual", "futures", "leverage", "liquidation", "delta",
        }
        return any(t in crypto_terms for t in tokens)
