"""
Model Trainer
=============
Orchestrates the full ML training pipeline:

  1. Collect labelled training data from candle history
  2. Train PricePredictor ensemble
  3. Train SignalClassifier
  4. Auto-train SentimentAnalyzer from emotion history
  5. Evaluate all models and return a unified report
  6. Schedule background retraining every N minutes

Also provides a single MLEngine.analyze() entry point used by
the server API and AI orchestrator.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from src.ml.feature_engineer import FeatureEngineer, FeatureVector
from src.ml.price_predictor import PricePredictor, PredictionResult
from src.ml.sentiment_analyzer import SentimentAnalyzer
from src.ml.anomaly_detector import AnomalyDetector, AnomalyReport
from src.ml.signal_classifier import SignalClassifier, SignalDecision
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MLAnalysis:
    """Full ML analysis result for one trading cycle."""

    # Sub-results
    prediction: PredictionResult
    signal: SignalDecision
    anomaly_report: AnomalyReport
    sentiment: Optional[Dict] = None

    # Current feature vector
    feature_vector: Optional[FeatureVector] = None

    # Training status
    is_trained: bool = False
    trained_samples: int = 0

    # Composite ML signal (-1 → +1)
    ml_composite_score: float = 0.0
    ml_action_suggestion: str = "HOLD"  # "BUY" | "SELL" | "HOLD"

    def to_dict(self) -> Dict:
        return {
            "prediction": self.prediction.to_dict(),
            "signal": self.signal.to_dict(),
            "anomaly_report": self.anomaly_report.to_dict(),
            "sentiment": self.sentiment,
            "is_trained": self.is_trained,
            "trained_samples": self.trained_samples,
            "ml_composite_score": round(self.ml_composite_score, 4),
            "ml_action_suggestion": self.ml_action_suggestion,
            "features": (self.feature_vector.to_dict() if self.feature_vector else {}),
        }


class MLEngine:
    """
    Central ML engine.  Instantiate once; call analyze() each cycle.

    Parameters
    ----------
    retrain_interval_min : auto-retrain every N minutes (default 60)
    min_candles_for_train: minimum candle history to attempt training
    """

    def __init__(
        self,
        retrain_interval_min: int = 60,
        min_candles_for_train: int = 200,
    ):
        self.retrain_interval = retrain_interval_min * 60
        self.min_candles = min_candles_for_train

        self.feature_eng = FeatureEngineer()
        self.predictor = PricePredictor()
        self.analyzer = SentimentAnalyzer()
        self.anomaly_det = AnomalyDetector()
        self.classifier = SignalClassifier()

        self._candle_history: List[Dict] = []
        self._sentiment_history: List[Dict] = []
        self._last_retrain: float = 0.0
        self._trained_n: int = 0

        logger.info(
            "MLEngine ready (retrain every %d min, min_candles=%d)",
            retrain_interval_min,
            min_candles_for_train,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        candles: List[Dict],
        sentiment: Optional[Dict] = None,
        geo: Optional[Dict] = None,
        current_price: Optional[float] = None,
    ) -> MLAnalysis:
        """
        Run the full ML pipeline on current market state.
        Call this once per trading cycle.
        """
        # Accumulate history for training
        if candles:
            self._candle_history = (self._candle_history + candles)[-2000:]
        if sentiment:
            self._sentiment_history.append(sentiment)
            self._sentiment_history = self._sentiment_history[-500:]

        # Auto-retrain if enough data and time has passed
        self._maybe_retrain()

        # Extract features from recent candles
        fv = self.feature_eng.extract(
            candles or self._candle_history[-200:],
            sentiment=sentiment,
            geo=geo,
            label_horizon=3,
        )

        current_sentiment_score = float((sentiment or {}).get("sentiment_score", 0))
        price = current_price or (candles[-1].get("close", 0) if candles else 0)

        # Anomaly detection
        anomaly_report = self.anomaly_det.detect(
            candles or self._candle_history[-100:],
            sentiment_score=current_sentiment_score,
            current_price=price,
        )

        # Price prediction
        if fv:
            prediction = self.predictor.predict(fv)
        else:
            from src.ml.price_predictor import PredictionResult

            prediction = PredictionResult(
                direction="flat",
                direction_int=0,
                prob_up=0.333,
                prob_down=0.333,
                prob_flat=0.334,
                confidence=0.0,
                model_agreement=0.0,
                is_trained=False,
                note="Insufficient candle history",
            )

        # Signal classification
        price_probs = (prediction.prob_up, prediction.prob_flat, prediction.prob_down)
        if fv:
            signal = self.classifier.classify(
                fv,
                price_pred_probs=price_probs,
                anomaly_risk=anomaly_report.risk_score,
            )
        else:
            from src.ml.signal_classifier import SignalDecision

            signal = SignalDecision(
                signal="HOLD",
                confidence=0.0,
                prob_buy=0.333,
                prob_sell=0.333,
                prob_hold=0.334,
                ml_score=0.0,
                anomaly_risk=anomaly_report.risk_score,
                is_trained=False,
                features_used=0,
                note="No feature vector available",
            )

        # Sentiment analysis on recent news headlines (if available)
        sent_result = None
        if sentiment and sentiment.get("reasoning"):
            sa = self.analyzer.analyze(sentiment["reasoning"])
            sent_result = sa.to_dict()

        # Composite ML score
        composite = self._composite_score(prediction, signal, anomaly_report)

        action = (
            "BUY" if composite >= 0.25 else ("SELL" if composite <= -0.25 else "HOLD")
        )
        if (
            anomaly_report.overall_risk in ("critical",)
            or anomaly_report.regime_change_detected
        ):
            action = "HOLD"

        return MLAnalysis(
            prediction=prediction,
            signal=signal,
            anomaly_report=anomaly_report,
            sentiment=sent_result,
            feature_vector=fv,
            is_trained=self.predictor._is_trained,
            trained_samples=self._trained_n,
            ml_composite_score=composite,
            ml_action_suggestion=action,
        )

    def train_now(
        self,
        candles: Optional[List[Dict]] = None,
        emotion_history: Optional[List[Dict]] = None,
    ) -> Dict:
        """Force an immediate retrain on all models."""
        source = candles or self._candle_history
        if len(source) < self.min_candles:
            return {
                "status": "insufficient_data",
                "candles": len(source),
                "required": self.min_candles,
            }

        logger.info("MLEngine: starting full retrain on %d candles…", len(source))
        t0 = time.time()

        # Feature extraction
        X, y = self.feature_eng.extract_batch(source, label_horizon=3)

        # Train PricePredictor
        pred_result = self.predictor.train(X, y)

        # Train SignalClassifier
        sig_result = self.classifier.train(X, y)

        # Train SentimentAnalyzer
        sent_result = {}
        if emotion_history or self._sentiment_history:
            sent_result = self.analyzer.auto_train_from_emotion_history(
                emotion_history or self._sentiment_history
            )

        self._trained_n = len(X)
        self._last_retrain = time.time()

        elapsed = time.time() - t0
        result = {
            "status": "trained",
            "candles": len(source),
            "labelled_samples": len(X),
            "price_predictor": pred_result,
            "signal_classifier": sig_result,
            "sentiment_analyzer": sent_result,
            "elapsed_sec": round(elapsed, 2),
        }
        logger.info("MLEngine retrain complete in %.1fs (%d samples)", elapsed, len(X))
        return result

    def analyze_headlines(self, texts: List[str]) -> Dict:
        """Analyze a batch of news headlines and return aggregated sentiment."""
        results = self.analyzer.analyze_batch(texts)
        agg = self.analyzer.aggregate(results)
        return {
            "aggregate": agg,
            "individual": [r.to_dict() for r in results[:20]],
        }

    def get_model_status(self) -> Dict:
        return {
            "price_predictor": {
                "trained": self.predictor._is_trained,
                "samples": self.predictor._trained_n,
                "top_features": dict(list(self.predictor._feature_imp.items())[:5]),
            },
            "signal_classifier": {
                "trained": self.classifier._is_trained,
                "samples": self.classifier._trained_n,
            },
            "sentiment_analyzer": {
                "trained": self.analyzer._is_trained,
                "vocab_size": len(self.analyzer._tfidf_vocab),
                "train_samples": self.analyzer._train_samples,
            },
            "anomaly_detector": self.anomaly_det.get_rolling_stats(),
            "candle_history_size": len(self._candle_history),
            "last_retrain": self._last_retrain,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _maybe_retrain(self):
        now = time.time()
        if (
            now - self._last_retrain > self.retrain_interval
            and len(self._candle_history) >= self.min_candles
        ):
            logger.info("MLEngine: scheduled auto-retrain triggered")
            self.train_now()

    @staticmethod
    def _composite_score(
        prediction: PredictionResult,
        signal: SignalDecision,
        anomaly_report: AnomalyReport,
    ) -> float:
        """Blend prediction + signal into a single -1→+1 score."""
        # Prediction contribution: +1=up, -1=down
        pred_score = prediction.prob_up - prediction.prob_down

        # Signal contribution
        sig_score = signal.ml_score  # already directional

        # Anomaly dampener
        dampener = 1.0 - anomaly_report.risk_score * 0.5

        blended = (pred_score * 0.55 + sig_score * 0.45) * dampener
        return float(np.clip(blended, -1.0, 1.0))
