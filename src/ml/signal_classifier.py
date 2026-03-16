"""
Signal Classifier
=================
ML-based BUY / SELL / HOLD signal generator.

Uses a soft-voting ensemble of:
  - RandomForestClassifier  (handles non-linear interactions)
  - GradientBoostingClassifier (boosted decision trees)
  - LogisticRegression (linear baseline with L2 regularisation)

Integrates:
  - ML price direction prediction (PricePredictor)
  - Anomaly risk score (AnomalyDetector)
  - Technical features (FeatureEngineer)
  - Sentiment score (SentimentAnalyzer)

Produces a final SignalDecision that complements TradingStrategy with
an ML-confidence layer.
"""

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional, Tuple

if TYPE_CHECKING:
    from src.ml.feature_engineer import FeatureVector

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

SIGNAL_LABELS = {0: "HOLD", 1: "BUY", 2: "SELL"}
SIGNAL_INT = {"HOLD": 0, "BUY": 1, "SELL": 2}


@dataclass
class SignalDecision:
    signal: str  # "BUY" | "SELL" | "HOLD"
    confidence: float  # 0.0 – 1.0
    prob_buy: float
    prob_sell: float
    prob_hold: float
    ml_score: float  # directional: +1=buy, -1=sell, 0=hold
    anomaly_risk: float  # 0.0 – 1.0 from AnomalyDetector
    is_trained: bool
    features_used: int
    note: str = ""

    @property
    def is_actionable(self) -> bool:
        return (
            self.is_trained
            and self.confidence >= 0.55
            and self.signal != "HOLD"
            and self.anomaly_risk < 0.7
        )

    def to_dict(self) -> Dict:
        return {
            "signal": self.signal,
            "confidence": round(self.confidence, 4),
            "prob_buy": round(self.prob_buy, 4),
            "prob_sell": round(self.prob_sell, 4),
            "prob_hold": round(self.prob_hold, 4),
            "ml_score": round(self.ml_score, 4),
            "anomaly_risk": round(self.anomaly_risk, 4),
            "is_trained": self.is_trained,
            "is_actionable": self.is_actionable,
            "features_used": self.features_used,
            "note": self.note,
        }


class SignalClassifier:
    """
    Three-class signal classifier (BUY / SELL / HOLD).

    The input feature vector is the FeatureEngineer output (30 features)
    augmented with:
      - PricePredictor confidence scores (3 additional features)
      - AnomalyDetector risk score       (1 additional feature)
      = 34 total input features

    Training uses the same labelled windows as PricePredictor, converting
    the regression label (+1/-1/0) into a classification label (BUY/SELL/HOLD).
    """

    MIN_TRAIN_SAMPLES = 60
    MODEL_FILE = os.path.join(MODEL_DIR, "signal_classifier.pkl")
    RETRAIN_INTERVAL = 600  # seconds

    def __init__(self):
        self._clf = None
        self._scaler = None
        self._is_trained = False
        self._trained_n = 0
        self._last_retrain = 0.0
        self._try_load()
        logger.info(
            "SignalClassifier initialised (trained=%s, n=%d)",
            self._is_trained,
            self._trained_n,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def classify(
        self,
        feature_vector: "FeatureVector",
        price_pred_probs: Optional[
            Tuple[float, float, float]
        ] = None,  # (up, flat, down)
        anomaly_risk: float = 0.0,
    ) -> SignalDecision:
        """Classify a single feature vector into BUY/SELL/HOLD."""

        # Augment features
        X_aug = self._augment(feature_vector.features, price_pred_probs, anomaly_risk)

        if not self._is_trained:
            return self._fallback(feature_vector, anomaly_risk)

        Xs = self._scaler.transform(X_aug)
        probs = self._clf.predict_proba(Xs)[0]  # (hold, buy, sell)

        # Map to named probabilities
        classes = list(self._clf.classes_)
        p = {c: float(probs[i]) for i, c in enumerate(classes)}
        p_buy = p.get(1, 0.0)
        p_sell = p.get(2, 0.0)
        p_hold = p.get(0, 0.0)

        # Penalise in high-anomaly environments
        if anomaly_risk > 0.5:
            dampen = 1 - (anomaly_risk - 0.5) * 0.5
            p_buy *= dampen
            p_sell *= dampen
            p_hold = 1 - p_buy - p_sell

        idx = int(np.argmax([p_hold, p_buy, p_sell]))
        signal = SIGNAL_LABELS[idx]
        conf = float(max(p_buy, p_sell, p_hold))
        ml_score = p_buy - p_sell  # directional: positive = buy, negative = sell

        return SignalDecision(
            signal=signal,
            confidence=conf,
            prob_buy=p_buy,
            prob_sell=p_sell,
            prob_hold=p_hold,
            ml_score=ml_score,
            anomaly_risk=anomaly_risk,
            is_trained=True,
            features_used=X_aug.shape[1],
        )

    def train(self, X: np.ndarray, y_direction: np.ndarray) -> Dict:
        """
        Train on (X, y_direction) where y_direction ∈ {+1, -1, 0}.
        Maps +1→BUY(1), -1→SELL(2), 0→HOLD(0).
        """
        if len(X) < self.MIN_TRAIN_SAMPLES:
            return {"status": "insufficient_data", "n": len(X)}

        try:
            from sklearn.ensemble import (
                RandomForestClassifier,
                GradientBoostingClassifier,
            )
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import cross_val_score
        except ImportError:
            return {"status": "sklearn_not_installed"}

        t0 = time.time()

        # Convert direction labels → class labels
        y = np.where(y_direction == 1, 1, np.where(y_direction == -1, 2, 0))

        self._scaler = StandardScaler()
        Xs = self._scaler.fit_transform(X)

        from sklearn.ensemble import VotingClassifier

        rf = RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        gb = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )
        lr = LogisticRegression(
            C=0.5,
            max_iter=500,
            multi_class="ovr",
            random_state=42,
        )
        self._clf = VotingClassifier(
            estimators=[("rf", rf), ("gb", gb), ("lr", lr)],
            voting="soft",
        )
        self._clf.fit(Xs, y)

        cv_scores = cross_val_score(rf, Xs, y, cv=min(5, len(X) // 12 + 1))

        self._is_trained = True
        self._trained_n = len(X)
        self._last_retrain = time.time()

        unique, counts = np.unique(y, return_counts=True)
        dist = {SIGNAL_LABELS[int(k)]: int(v) for k, v in zip(unique, counts)}

        self._save()
        elapsed = time.time() - t0
        result = {
            "status": "trained",
            "samples": len(X),
            "cv_accuracy": round(float(np.mean(cv_scores)), 4),
            "class_distribution": dist,
            "elapsed_sec": round(elapsed, 2),
        }
        logger.info(
            "SignalClassifier trained: acc=%.3f in %.1fs",
            result["cv_accuracy"],
            elapsed,
        )
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _augment(
        features: np.ndarray,
        price_pred_probs: Optional[Tuple],
        anomaly_risk: float,
    ) -> np.ndarray:
        extra = []
        if price_pred_probs is not None:
            extra.extend(list(price_pred_probs))  # up, flat, down
        else:
            extra.extend([0.333, 0.334, 0.333])
        extra.append(anomaly_risk)
        return np.concatenate([features, extra]).reshape(1, -1)

    def _fallback(self, fv: "FeatureVector", anomaly_risk: float) -> SignalDecision:
        """Rule-based fallback when model is not yet trained."""
        # Use the direction label from FeatureEngineer if available
        label = fv.label if fv.label is not None else 0
        signal = {1: "BUY", -1: "SELL", 0: "HOLD"}.get(label, "HOLD")
        return SignalDecision(
            signal=signal,
            confidence=0.4,
            prob_buy=0.333,
            prob_sell=0.333,
            prob_hold=0.334,
            ml_score=0.0,
            anomaly_risk=anomaly_risk,
            is_trained=False,
            features_used=len(fv.features),
            note="Not yet trained — showing rule-based fallback",
        )

    def _save(self):
        try:
            import joblib

            joblib.dump(
                {
                    "clf": self._clf,
                    "scaler": self._scaler,
                    "trained_n": self._trained_n,
                },
                self.MODEL_FILE,
            )
        except Exception as e:
            logger.warning("Could not save SignalClassifier: %s", e)

    def _try_load(self):
        if not os.path.exists(self.MODEL_FILE):
            return
        try:
            import joblib

            d = joblib.load(self.MODEL_FILE)
            self._clf, self._scaler = d["clf"], d["scaler"]
            self._trained_n = d.get("trained_n", 0)
            self._is_trained = True
            logger.info("SignalClassifier loaded from disk (n=%d)", self._trained_n)
        except Exception as e:
            logger.warning("Could not load SignalClassifier: %s", e)
