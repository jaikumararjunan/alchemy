"""
Anomaly Detector
================
Detects statistical anomalies in price, volume, and sentiment data using:

  1. Z-Score detector        : flags observations beyond N standard deviations
  2. IQR detector            : robust outlier detection via interquartile range
  3. CUSUM detector          : cumulative sum change-point detection (regime shifts)
  4. Rolling-window detector : combination of the above with adaptive thresholds
  5. Multi-signal detector   : cross-validates anomalies across price+volume+sentiment

All algorithms are pure-Python / NumPy — no additional ML dependencies.

Anomaly types:
  - PRICE_SPIKE    : sudden large price movement
  - VOLUME_SURGE   : unusual trading volume
  - VOLATILITY_JUMP: ATR expansion beyond normal range
  - SENTIMENT_SHIFT: abrupt change in sentiment signal
  - REGIME_CHANGE  : CUSUM detects structural break (trending ↔ ranging)
  - CORR_BREAKDOWN : price-volume correlation breakdown
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Anomaly:
    anomaly_type: str  # see module docstring
    severity: str  # "low" | "medium" | "high" | "critical"
    z_score: float
    value: float
    baseline_mean: float
    baseline_std: float
    description: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    trading_implication: str = ""

    def to_dict(self) -> Dict:
        return {
            "type": self.anomaly_type,
            "severity": self.severity,
            "z_score": round(self.z_score, 3),
            "value": round(self.value, 4),
            "baseline_mean": round(self.baseline_mean, 4),
            "baseline_std": round(self.baseline_std, 6),
            "description": self.description,
            "trading_implication": self.trading_implication,
            "timestamp": self.timestamp,
        }


@dataclass
class AnomalyReport:
    anomalies: List[Anomaly] = field(default_factory=list)
    overall_risk: str = "normal"  # "normal"|"elevated"|"high"|"critical"
    risk_score: float = 0.0  # 0.0 – 1.0
    regime_change_detected: bool = False
    cusum_stat: float = 0.0
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "anomalies": [a.to_dict() for a in self.anomalies],
            "overall_risk": self.overall_risk,
            "risk_score": round(self.risk_score, 4),
            "anomaly_count": len(self.anomalies),
            "regime_change_detected": self.regime_change_detected,
            "cusum_stat": round(self.cusum_stat, 4),
            "summary": self.summary,
        }


class AnomalyDetector:
    """
    Stateful anomaly detector.  Maintains a rolling history and
    adaptively updates baselines as new data arrives.

    Parameters
    ----------
    window        : rolling window size for baseline stats (default 100)
    z_threshold   : standard deviations for flagging (default 2.5)
    iqr_factor    : IQR multiplier for outlier fence (default 2.0)
    cusum_target  : CUSUM target shift magnitude in σ (default 0.5)
    cusum_limit   : CUSUM control limit in σ (default 4.0)
    """

    def __init__(
        self,
        window: int = 100,
        z_threshold: float = 2.5,
        iqr_factor: float = 2.0,
        cusum_target: float = 0.5,
        cusum_limit: float = 4.0,
    ):
        self.window = window
        self.z_threshold = z_threshold
        self.iqr_factor = iqr_factor
        self.cusum_target = cusum_target
        self.cusum_limit = cusum_limit

        # Rolling histories
        self._price_returns: List[float] = []
        self._volumes: List[float] = []
        self._atrs: List[float] = []
        self._sentiment_scores: List[float] = []

        # CUSUM state
        self._cusum_pos = 0.0  # detects upward shifts
        self._cusum_neg = 0.0  # detects downward shifts

        logger.info(
            "AnomalyDetector initialised (window=%d, z=%.1f)", window, z_threshold
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def detect(
        self,
        candles: List[Dict],
        sentiment_score: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> AnomalyReport:
        """
        Run all detectors on the latest candle + optional sentiment signal.
        Returns an AnomalyReport.
        """
        if len(candles) < 20:
            return AnomalyReport(summary="Insufficient data")

        closes = np.array([float(c.get("close", c.get("c", 0))) for c in candles])
        volumes = np.array([float(c.get("volume", c.get("v", 0))) for c in candles])

        # Compute current period metrics
        ret = float((closes[-1] - closes[-2]) / closes[-2]) if closes[-2] != 0 else 0.0
        atr = float(np.mean(np.abs(np.diff(closes[-15:]))))

        # Update rolling state
        self._price_returns.append(ret)
        self._volumes.append(float(volumes[-1]))
        self._atrs.append(atr)
        if sentiment_score is not None:
            self._sentiment_scores.append(sentiment_score)

        # Trim to window
        self._price_returns = self._price_returns[-self.window :]
        self._volumes = self._volumes[-self.window :]
        self._atrs = self._atrs[-self.window :]
        self._sentiment_scores = self._sentiment_scores[-self.window :]

        anomalies: List[Anomaly] = []

        # ── 1. Price return anomaly ───────────────────────────────────────────
        if len(self._price_returns) >= 10:
            a = self._z_detect(
                series=self._price_returns,
                current=ret,
                anom_type="PRICE_SPIKE",
                label=f"Return {ret * 100:+.2f}%",
                implication="Possible momentum entry or stop-hunt; widen SL",
            )
            if a:
                anomalies.append(a)

        # ── 2. Volume anomaly ─────────────────────────────────────────────────
        if len(self._volumes) >= 10:
            a = self._z_detect(
                series=self._volumes,
                current=float(volumes[-1]),
                anom_type="VOLUME_SURGE",
                label=f"Volume {volumes[-1]:,.0f}",
                implication="High conviction move; increases signal reliability",
            )
            if a:
                anomalies.append(a)

        # ── 3. Volatility (ATR) anomaly ───────────────────────────────────────
        if len(self._atrs) >= 10:
            a = self._z_detect(
                series=self._atrs,
                current=atr,
                anom_type="VOLATILITY_JUMP",
                label=f"ATR expansion {atr / closes[-1] * 100:.3f}%",
                implication="Widen stops; reduce position size; possible regime change",
            )
            if a:
                anomalies.append(a)

        # ── 4. Sentiment shift ────────────────────────────────────────────────
        if sentiment_score is not None and len(self._sentiment_scores) >= 10:
            a = self._z_detect(
                series=self._sentiment_scores,
                current=sentiment_score,
                anom_type="SENTIMENT_SHIFT",
                label=f"Sentiment {sentiment_score:+.3f}",
                implication="Macro narrative shift; re-evaluate directional bias",
            )
            if a:
                anomalies.append(a)

        # ── 5. CUSUM regime-change detector ──────────────────────────────────
        cusum_stat, regime_change = self._cusum(ret)

        # ── 6. Price-volume correlation breakdown ─────────────────────────────
        if len(closes) >= 20:
            a = self._correlation_check(closes[-20:], volumes[-20:])
            if a:
                anomalies.append(a)

        # ── Aggregate risk ────────────────────────────────────────────────────
        critical_count = sum(1 for a in anomalies if a.severity in ("high", "critical"))
        risk_score = min(len(anomalies) * 0.15 + critical_count * 0.25, 1.0)

        if regime_change:
            risk_score = min(risk_score + 0.3, 1.0)

        if risk_score >= 0.8:
            overall = "critical"
        elif risk_score >= 0.5:
            overall = "high"
        elif risk_score >= 0.25:
            overall = "elevated"
        else:
            overall = "normal"

        summary = self._build_summary(anomalies, regime_change, overall)

        logger.debug(
            "AnomalyDetector: %d anomalies | risk=%s (%.2f) | cusum=%.2f | regime_change=%s",
            len(anomalies),
            overall,
            risk_score,
            cusum_stat,
            regime_change,
        )

        return AnomalyReport(
            anomalies=anomalies,
            overall_risk=overall,
            risk_score=risk_score,
            regime_change_detected=regime_change,
            cusum_stat=cusum_stat,
            summary=summary,
        )

    def get_rolling_stats(self) -> Dict:
        """Return current rolling baseline statistics."""

        def _stats(arr):
            if len(arr) < 3:
                return {"mean": 0, "std": 0, "min": 0, "max": 0, "n": len(arr)}
            a = np.array(arr)
            return {
                "mean": round(float(np.mean(a)), 6),
                "std": round(float(np.std(a, ddof=1)), 6),
                "min": round(float(np.min(a)), 6),
                "max": round(float(np.max(a)), 6),
                "n": len(arr),
            }

        return {
            "price_returns": _stats(self._price_returns),
            "volumes": _stats(self._volumes),
            "atrs": _stats(self._atrs),
            "sentiment": _stats(self._sentiment_scores),
            "cusum_pos": round(self._cusum_pos, 4),
            "cusum_neg": round(self._cusum_neg, 4),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _z_detect(
        self,
        series: List[float],
        current: float,
        anom_type: str,
        label: str,
        implication: str,
    ) -> Optional[Anomaly]:
        arr = np.array(series[:-1])  # exclude current from baseline
        if len(arr) < 5:
            return None
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=1))
        if std < 1e-10:
            return None

        z = (current - mean) / std
        if abs(z) < self.z_threshold:
            return None

        # Also check IQR
        q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
        iqr = q3 - q1
        iqr_anomaly = (
            current < q1 - self.iqr_factor * iqr or current > q3 + self.iqr_factor * iqr
        )

        if abs(z) >= 4.0 or (abs(z) >= self.z_threshold and iqr_anomaly):
            severity = "critical" if abs(z) >= 5 else "high"
        elif abs(z) >= 3.0:
            severity = "medium"
        else:
            severity = "low"

        return Anomaly(
            anomaly_type=anom_type,
            severity=severity,
            z_score=round(z, 3),
            value=current,
            baseline_mean=mean,
            baseline_std=std,
            description=f"{anom_type}: {label} (z={z:+.2f}, σ={std:.5f})",
            trading_implication=implication,
        )

    def _cusum(self, new_value: float) -> Tuple[float, bool]:
        """
        CUSUM change-point detection.
        Returns (combined_stat, regime_change_detected).
        """
        if len(self._price_returns) < 20:
            return 0.0, False

        baseline = np.array(self._price_returns[:-1])
        mu = float(np.mean(baseline))
        sigma = float(np.std(baseline, ddof=1))
        if sigma < 1e-10:
            return 0.0, False

        z = (new_value - mu) / sigma
        self._cusum_pos = max(0.0, self._cusum_pos + z - self.cusum_target)
        self._cusum_neg = max(0.0, self._cusum_neg - z - self.cusum_target)

        combined = max(self._cusum_pos, self._cusum_neg)
        detected = combined > self.cusum_limit

        if detected:
            logger.info(
                "CUSUM regime change detected: stat=%.2f (limit=%.1f)",
                combined,
                self.cusum_limit,
            )
            # Reset after detection
            self._cusum_pos = 0.0
            self._cusum_neg = 0.0

        return combined, detected

    @staticmethod
    def _correlation_check(
        closes: np.ndarray, volumes: np.ndarray
    ) -> Optional[Anomaly]:
        """Detect price-volume correlation breakdown (divergence signal)."""
        if len(closes) < 15:
            return None
        price_rets = np.diff(closes)
        vol_chg = np.diff(volumes)
        if len(price_rets) < 10:
            return None
        corr = float(np.corrcoef(price_rets, vol_chg)[0, 1])
        if np.isnan(corr):
            return None
        # Typical positive correlation; strong negative is anomalous
        if corr < -0.6:
            return Anomaly(
                anomaly_type="CORR_BREAKDOWN",
                severity="medium",
                z_score=corr,
                value=corr,
                baseline_mean=0.2,
                baseline_std=0.3,
                description=f"Price-volume correlation breakdown: corr={corr:.3f}",
                trading_implication="Possible smart money divergence; be cautious on breakouts",
            )
        return None

    @staticmethod
    def _build_summary(
        anomalies: List[Anomaly], regime_change: bool, overall: str
    ) -> str:
        if not anomalies and not regime_change:
            return "No anomalies detected. Market conditions normal."
        parts = []
        if regime_change:
            parts.append("REGIME CHANGE detected by CUSUM")
        for a in anomalies:
            parts.append(f"{a.anomaly_type} [{a.severity.upper()}] z={a.z_score:+.2f}")
        return " | ".join(parts) if parts else f"Risk level: {overall}"
