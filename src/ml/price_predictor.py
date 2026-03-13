"""
Price Direction Predictor
=========================
Ensemble model: RandomForest + GradientBoosting → LogisticRegression meta-learner.
Predicts 3-period ahead price direction: +1 (up), -1 (down), 0 (flat).

Design principles:
  - No external model downloads; trains on runtime candle history
  - Persists trained models to disk (joblib) for hot-reload across restarts
  - Exposes an online_update() method for incremental learning each cycle
  - Returns calibrated probabilities + feature importances
"""

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from src.ml.feature_engineer import FeatureVector

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)


@dataclass
class PredictionResult:
    direction: str  # "up" | "down" | "flat"
    direction_int: int  # +1, -1, 0
    prob_up: float
    prob_down: float
    prob_flat: float
    confidence: float  # max(prob_up, prob_down) — flat doesn't count
    model_agreement: float  # fraction of ensemble members agreeing with direction
    feature_importances: Dict[str, float] = field(default_factory=dict)
    trained_samples: int = 0
    is_trained: bool = False
    note: str = ""

    @property
    def is_actionable(self) -> bool:
        """True when model is trained and confident enough to trade on."""
        return self.is_trained and self.confidence >= 0.60

    def to_dict(self) -> Dict:
        return {
            "direction": self.direction,
            "direction_int": self.direction_int,
            "prob_up": round(self.prob_up, 4),
            "prob_down": round(self.prob_down, 4),
            "prob_flat": round(self.prob_flat, 4),
            "confidence": round(self.confidence, 4),
            "model_agreement": round(self.model_agreement, 4),
            "is_actionable": self.is_actionable,
            "trained_samples": self.trained_samples,
            "is_trained": self.is_trained,
            "top_features": dict(
                sorted(self.feature_importances.items(), key=lambda x: -x[1])[:10]
            ),
            "note": self.note,
        }


class PricePredictor:
    """
    Two-level ensemble price direction predictor.

    Level 1  : RandomForest + GradientBoosting + ExtraTrees
    Level 2  : LogisticRegression meta-learner on L1 probability outputs
    Training : triggered automatically when ≥ MIN_TRAIN_SAMPLES are available.
    """

    MIN_TRAIN_SAMPLES = 50  # minimum labelled samples to train
    RETRAIN_INTERVAL = 300  # seconds between auto-retrain checks
    MODEL_FILE = os.path.join(MODEL_DIR, "price_predictor.pkl")

    def __init__(self):
        self._rf = None  # RandomForestClassifier
        self._gb = None  # GradientBoostingClassifier
        self._et = None  # ExtraTreesClassifier
        self._meta = None  # LogisticRegression meta-learner
        self._scaler = None
        self._is_trained = False
        self._trained_n = 0
        self._last_retrain = 0.0
        self._feature_imp: Dict[str, float] = {}
        self._classes = np.array([-1, 0, 1])
        self._try_load()
        logger.info(
            "PricePredictor initialised (trained=%s, n=%d)",
            self._is_trained,
            self._trained_n,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def predict(self, feature_vector: "FeatureVector") -> PredictionResult:
        """Predict direction for a single feature vector."""
        if not self._is_trained:
            return self._untrained()

        X = self._scaler.transform(feature_vector.X)
        probs = self._ensemble_proba(X)[0]  # shape (3,) → [-1, 0, +1]
        idx = int(np.argmax(probs))
        dirs = {0: ("down", -1), 1: ("flat", 0), 2: ("up", 1)}
        direction, dir_int = dirs[idx]
        conf = float(max(probs[0], probs[2]))  # ignore flat

        # Agreement across base learners
        agree = self._agreement(X, dir_int)

        return PredictionResult(
            direction=direction,
            direction_int=dir_int,
            prob_up=float(probs[2]),
            prob_down=float(probs[0]),
            prob_flat=float(probs[1]),
            confidence=conf,
            model_agreement=agree,
            feature_importances=self._feature_imp,
            trained_samples=self._trained_n,
            is_trained=True,
        )

    def train(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """Full training on (X, y) arrays (from FeatureEngineer.extract_batch)."""
        if len(X) < self.MIN_TRAIN_SAMPLES:
            logger.warning(
                "PricePredictor: only %d samples — need %d",
                len(X),
                self.MIN_TRAIN_SAMPLES,
            )
            return {"status": "insufficient_data", "samples": len(X)}

        try:
            from sklearn.ensemble import (
                RandomForestClassifier,
                GradientBoostingClassifier,
                ExtraTreesClassifier,
            )
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import cross_val_score
        except ImportError:
            logger.error("scikit-learn not installed — pip install scikit-learn")
            return {"status": "sklearn_not_installed"}

        logger.info("PricePredictor: training on %d samples…", len(X))
        t0 = time.time()

        # Scale
        self._scaler = StandardScaler()
        Xs = self._scaler.fit_transform(X)

        # Base learners
        self._rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        self._gb = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )
        self._et = ExtraTreesClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        self._rf.fit(Xs, y)
        self._gb.fit(Xs, y)
        self._et.fit(Xs, y)

        # Meta-learner
        Z = self._base_proba(Xs)
        self._meta = LogisticRegression(C=1.0, max_iter=500, random_state=42)
        self._meta.fit(Z, y)

        # Metrics
        cv_scores = cross_val_score(self._rf, Xs, y, cv=min(5, len(X) // 10 + 1))

        # Feature importance (average across RF + ET)
        from src.ml.feature_engineer import FEATURE_NAMES

        imp = (self._rf.feature_importances_ + self._et.feature_importances_) / 2
        self._feature_imp = {n: round(float(v), 5) for n, v in zip(FEATURE_NAMES, imp)}

        self._is_trained = True
        self._trained_n = len(X)
        self._last_retrain = time.time()

        # Class distribution
        unique, counts = np.unique(y, return_counts=True)
        dist = {int(k): int(v) for k, v in zip(unique, counts)}

        self._save()
        elapsed = time.time() - t0
        result = {
            "status": "trained",
            "samples": len(X),
            "cv_accuracy": round(float(np.mean(cv_scores)), 4),
            "cv_std": round(float(np.std(cv_scores)), 4),
            "class_distribution": dist,
            "top_features": dict(
                list(sorted(self._feature_imp.items(), key=lambda x: -x[1]))[:10]
            ),
            "elapsed_sec": round(elapsed, 2),
        }
        logger.info(
            "PricePredictor trained: acc=%.3f±%.3f in %.1fs",
            result["cv_accuracy"],
            result["cv_std"],
            elapsed,
        )
        return result

    def online_update(self, X_new: np.ndarray, y_new: np.ndarray):
        """Warm-start incremental update (RF doesn't support true online — retrain if enough new data)."""
        if len(X_new) < 5:
            return
        now = time.time()
        if now - self._last_retrain > self.RETRAIN_INTERVAL:
            logger.info(
                "PricePredictor: scheduled retrain with %d new samples", len(X_new)
            )
            self.train(X_new, y_new)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _base_proba(self, Xs: np.ndarray) -> np.ndarray:
        p_rf = self._rf.predict_proba(Xs)
        p_gb = self._gb.predict_proba(Xs)
        p_et = self._et.predict_proba(Xs)
        return np.hstack([p_rf, p_gb, p_et])

    def _ensemble_proba(self, Xs: np.ndarray) -> np.ndarray:
        if self._meta:
            Z = self._base_proba(Xs)
            return self._meta.predict_proba(Z)
        # Fallback: average base probabilities
        p_rf = self._rf.predict_proba(Xs)
        p_gb = self._gb.predict_proba(Xs)
        p_et = self._et.predict_proba(Xs)
        return (p_rf + p_gb + p_et) / 3

    def _agreement(self, Xs: np.ndarray, direction: int) -> float:
        preds = [m.predict(Xs)[0] for m in [self._rf, self._gb, self._et]]
        agreeing = sum(1 for p in preds if p == direction)
        return agreeing / len(preds)

    @staticmethod
    def _untrained() -> PredictionResult:
        return PredictionResult(
            direction="flat",
            direction_int=0,
            prob_up=0.333,
            prob_down=0.333,
            prob_flat=0.334,
            confidence=0.0,
            model_agreement=0.0,
            is_trained=False,
            note="Model not yet trained — need ≥ 50 labelled candle windows",
        )

    def _save(self):
        try:
            import joblib

            joblib.dump(
                {
                    "rf": self._rf,
                    "gb": self._gb,
                    "et": self._et,
                    "meta": self._meta,
                    "scaler": self._scaler,
                    "trained_n": self._trained_n,
                    "feature_imp": self._feature_imp,
                },
                self.MODEL_FILE,
            )
            logger.debug("PricePredictor saved to %s", self.MODEL_FILE)
        except Exception as e:
            logger.warning("Could not save PricePredictor: %s", e)

    def _try_load(self):
        if not os.path.exists(self.MODEL_FILE):
            return
        try:
            import joblib

            d = joblib.load(self.MODEL_FILE)
            self._rf, self._gb, self._et = d["rf"], d["gb"], d["et"]
            self._meta = d.get("meta")
            self._scaler = d["scaler"]
            self._trained_n = d.get("trained_n", 0)
            self._feature_imp = d.get("feature_imp", {})
            self._is_trained = True
            logger.info("PricePredictor loaded from disk (n=%d)", self._trained_n)
        except Exception as e:
            logger.warning("Could not load saved PricePredictor: %s", e)
