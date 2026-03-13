"""
Feature Engineering Pipeline
=============================
Extracts a rich feature vector from raw OHLCV candle data combined with
sentiment / geopolitical signals for downstream ML models.

Feature groups (30+ features total):
  Price features    : returns (1/3/5/10 bars), log-returns, price position in range
  Momentum          : RSI-14, RSI-7, MACD, MACD signal, MACD histogram
  Volatility        : ATR-14, BB width, BB %B, historical vol (10/20 bar)
  Volume            : OBV, volume ratio (5/20 bar), volume momentum
  Trend             : SMA cross (10/20), EMA cross (5/20), ADX-like proxy
  Candle patterns   : doji, hammer, engulf, upper/lower shadow ratios
  Market microstr.  : bid-ask spread pct, mark vs last price deviation
  Sentiment         : emotion score, crypto sentiment, confidence, geo impact
  Derived           : trend * momentum interaction, vol-adjusted momentum
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

FEATURE_NAMES = [
    # Returns
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_10",
    "log_ret_1",
    "log_ret_5",
    # Price position
    "price_pos_10",  # (close - low10) / (high10 - low10)
    "price_pos_20",
    # RSI
    "rsi_7",
    "rsi_14",
    # MACD
    "macd",
    "macd_signal",
    "macd_hist",
    # Bollinger
    "bb_width_20",
    "bb_pct_b_20",
    # ATR / volatility
    "atr_14_pct",  # ATR as % of price
    "hist_vol_10",
    "hist_vol_20",
    # Volume
    "obv_change_5",  # OBV momentum (5-bar change normalised)
    "vol_ratio_5",
    "vol_ratio_20",
    # Trend / SMA crosses
    "sma_10_20_cross",  # (SMA10 - SMA20) / price
    "ema_5_20_cross",
    "close_above_sma20",  # binary
    # Candle patterns
    "body_size",  # |close - open| / (high - low)
    "upper_shadow",  # (high - max(open,close)) / (high - low)
    "lower_shadow",  # (min(open,close) - low) / (high - low)
    # Sentiment
    "emo_score",
    "crypto_sentiment",
    "emo_confidence",
    "geo_impact",
    # Interactions
    "vol_adj_momentum",  # ret_5 / hist_vol_10
    "trend_momentum",  # sma_cross * rsi_14_norm
]


@dataclass
class FeatureVector:
    """Named feature array for one time-step."""

    features: np.ndarray
    feature_names: List[str]
    timestamp: Optional[str] = None
    label: Optional[int] = None  # +1 = up, -1 = down, 0 = flat (for training)
    label_pct: Optional[float] = None  # actual next-period return

    def to_dict(self) -> Dict[str, float]:
        return {k: float(v) for k, v in zip(self.feature_names, self.features)}

    @property
    def X(self) -> np.ndarray:
        """2-D row vector for sklearn."""
        return self.features.reshape(1, -1)


class FeatureEngineer:
    """
    Stateless feature extractor.  Call extract() with a candle list and
    optional sentiment/geo dicts to get a FeatureVector.
    """

    MIN_CANDLES = 25  # minimum history required

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(
        self,
        candles: List[Dict],
        sentiment: Optional[Dict] = None,
        geo: Optional[Dict] = None,
        label_horizon: int = 3,  # periods ahead to create label
        label_threshold_pct: float = 0.3,
    ) -> Optional["FeatureVector"]:
        """
        Extract features from *candles* (oldest first).
        Returns None if not enough history.
        """
        if len(candles) < self.MIN_CANDLES:
            return None

        c = [self._parse(x) for x in candles]
        closes = np.array([x["close"] for x in c])
        opens = np.array([x["open"] for x in c])
        highs = np.array([x["high"] for x in c])
        lows = np.array([x["low"] for x in c])
        vols = np.array([x["volume"] for x in c])

        price = closes[-1]
        if price == 0:
            return None

        feats: List[float] = []

        # ── Returns ──────────────────────────────────────────────────────────
        feats.append(self._ret(closes, 1))
        feats.append(self._ret(closes, 3))
        feats.append(self._ret(closes, 5))
        feats.append(self._ret(closes, 10))
        feats.append(self._log_ret(closes, 1))
        feats.append(self._log_ret(closes, 5))

        # ── Price position ────────────────────────────────────────────────────
        feats.append(self._price_pos(closes, highs, lows, 10))
        feats.append(self._price_pos(closes, highs, lows, 20))

        # ── RSI ───────────────────────────────────────────────────────────────
        feats.append(self._rsi(closes, 7))
        feats.append(self._rsi(closes, 14))

        # ── MACD ─────────────────────────────────────────────────────────────
        macd, signal, hist = self._macd(closes)
        feats.extend([macd / price, signal / price, hist / price])

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb_w, bb_pct = self._bollinger(closes, 20)
        feats.extend([bb_w, bb_pct])

        # ── ATR / Volatility ─────────────────────────────────────────────────
        atr = self._atr(highs, lows, closes, 14)
        feats.append(atr / price)
        feats.append(self._hist_vol(closes, 10))
        feats.append(self._hist_vol(closes, 20))

        # ── Volume ────────────────────────────────────────────────────────────
        obv = self._obv(closes, vols)
        obv_chg = (obv[-1] - obv[-6]) / (abs(obv[-6]) + 1e-9)
        feats.append(np.clip(obv_chg, -5, 5))
        feats.append(self._vol_ratio(vols, 5))
        feats.append(self._vol_ratio(vols, 20))

        # ── Trend / SMA crosses ───────────────────────────────────────────────
        sma10 = float(np.mean(closes[-10:]))
        sma20 = float(np.mean(closes[-20:]))
        ema5 = self._ema(closes, 5)
        ema20 = self._ema(closes, 20)
        feats.append((sma10 - sma20) / price)
        feats.append((ema5 - ema20) / price)
        feats.append(1.0 if price > sma20 else -1.0)

        # ── Candle patterns ───────────────────────────────────────────────────
        rng = highs[-1] - lows[-1]
        if rng > 0:
            body = abs(closes[-1] - opens[-1]) / rng
            up = (highs[-1] - max(closes[-1], opens[-1])) / rng
            dn = (min(closes[-1], opens[-1]) - lows[-1]) / rng
        else:
            body, up, dn = 0.0, 0.0, 0.0
        feats.extend([body, up, dn])

        # ── Sentiment ─────────────────────────────────────────────────────────
        sent = sentiment or {}
        geo_ = geo or {}
        feats.append(float(sent.get("sentiment_score", 0)))
        feats.append(
            float(
                sent.get("crypto_specific_sentiment", sent.get("crypto_sentiment", 0))
            )
        )
        feats.append(float(sent.get("confidence", 0.5)))
        feats.append(float(geo_.get("total_impact", 0)))

        # ── Interaction features ──────────────────────────────────────────────
        ret5 = self._ret(closes, 5)
        hvol10 = self._hist_vol(closes, 10)
        rsi14 = self._rsi(closes, 14)
        feats.append(ret5 / (hvol10 + 1e-9))  # vol-adjusted momentum
        feats.append(((sma10 - sma20) / price) * (rsi14 / 50 - 1))  # trend × RSI

        arr = np.array(feats, dtype=np.float32)
        arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
        arr = np.clip(arr, -10.0, 10.0)

        # ── Label (for training data) ─────────────────────────────────────────
        label, label_pct = None, None
        if len(closes) > label_horizon:
            fwd_ret = (closes[-1] - closes[-(label_horizon + 1)]) / closes[
                -(label_horizon + 1)
            ]
            label_pct = float(fwd_ret)
            t = label_threshold_pct / 100
            label = 1 if fwd_ret > t else (-1 if fwd_ret < -t else 0)

        return FeatureVector(
            features=arr,
            feature_names=FEATURE_NAMES,
            label=label,
            label_pct=label_pct,
        )

    def extract_batch(
        self,
        candles: List[Dict],
        sentiment_list: Optional[List[Dict]] = None,
        geo_list: Optional[List[Dict]] = None,
        label_horizon: int = 3,
        label_threshold_pct: float = 0.3,
        step: int = 1,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Slide a window over *candles* to produce (X, y) training arrays.
        Returns (X: [n_samples, n_features], y: [n_samples]) for sklearn.
        """
        X, y = [], []
        n = len(candles)
        for i in range(self.MIN_CANDLES, n - label_horizon, step):
            window = candles[max(0, i - 100) : i + label_horizon]
            sent = (
                sentiment_list[i]
                if sentiment_list and i < len(sentiment_list)
                else None
            )
            geo = geo_list[i] if geo_list and i < len(geo_list) else None
            fv = self.extract(window, sent, geo, label_horizon, label_threshold_pct)
            if fv is not None and fv.label is not None:
                X.append(fv.features)
                y.append(fv.label)
        if not X:
            return np.empty((0, len(FEATURE_NAMES))), np.empty(0)
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse(c: Dict) -> Dict:
        return {
            "close": float(c.get("close", c.get("c", 0))),
            "open": float(c.get("open", c.get("o", 0))),
            "high": float(c.get("high", c.get("h", 0))),
            "low": float(c.get("low", c.get("l", 0))),
            "volume": float(c.get("volume", c.get("v", 0))),
        }

    @staticmethod
    def _ret(closes: np.ndarray, n: int) -> float:
        if len(closes) <= n or closes[-n - 1] == 0:
            return 0.0
        return float((closes[-1] - closes[-n - 1]) / closes[-n - 1])

    @staticmethod
    def _log_ret(closes: np.ndarray, n: int) -> float:
        if len(closes) <= n or closes[-n - 1] <= 0 or closes[-1] <= 0:
            return 0.0
        return float(math.log(closes[-1] / closes[-n - 1]))

    @staticmethod
    def _price_pos(
        closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, n: int
    ) -> float:
        h, lo = float(np.max(highs[-n:])), float(np.min(lows[-n:]))
        if h == lo:
            return 0.5
        return float((closes[-1] - lo) / (h - lo))

    @staticmethod
    def _rsi(closes: np.ndarray, period: int) -> float:
        if len(closes) < period + 1:
            return 50.0
        diff = np.diff(closes[-(period + 1) :])
        gains = np.where(diff > 0, diff, 0)
        loses = np.where(diff < 0, -diff, 0)
        ag, al = np.mean(gains), np.mean(loses)
        if al == 0:
            return 100.0
        return float(100 - 100 / (1 + ag / al))

    @staticmethod
    def _ema(closes: np.ndarray, period: int) -> float:
        if len(closes) < period:
            return float(closes[-1])
        k = 2 / (period + 1)
        ema = float(np.mean(closes[:period]))
        for v in closes[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    def _macd(self, closes: np.ndarray, fast: int = 12, slow: int = 26, sig: int = 9):
        if len(closes) < slow + sig:
            return 0.0, 0.0, 0.0
        ema_fast = self._ema(closes, fast)
        ema_slow = self._ema(closes, slow)
        macd = ema_fast - ema_slow
        # approximate signal as EMA of last 9 macd values
        macd_arr = np.array(
            [
                self._ema(
                    closes[: -(slow - i) if (slow - i) > 0 else len(closes)], fast
                )
                - self._ema(
                    closes[: -(slow - i) if (slow - i) > 0 else len(closes)], slow
                )
                for i in range(sig + 1)
            ]
        )
        signal = float(np.mean(macd_arr[-sig:]))
        return float(macd), signal, float(macd - signal)

    @staticmethod
    def _bollinger(closes: np.ndarray, period: int = 20):
        if len(closes) < period:
            return 0.0, 0.5
        w = closes[-period:]
        m = float(np.mean(w))
        s = float(np.std(w, ddof=1))
        if m == 0 or s == 0:
            return 0.0, 0.5
        width = (2 * s) / m  # width as % of mid
        pct_b = (closes[-1] - (m - 2 * s)) / (4 * s) if s > 0 else 0.5
        return float(width), float(np.clip(pct_b, 0, 1))

    @staticmethod
    def _atr(
        highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int
    ) -> float:
        if len(closes) < period + 1:
            return 0.0
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1]),
            ),
        )
        return float(np.mean(tr[-period:]))

    @staticmethod
    def _hist_vol(closes: np.ndarray, period: int) -> float:
        if len(closes) < period + 1:
            return 0.0
        rets = np.diff(np.log(np.maximum(closes[-(period + 1) :], 1e-9)))
        return float(np.std(rets, ddof=1)) if len(rets) >= 2 else 0.0

    @staticmethod
    def _obv(closes: np.ndarray, vols: np.ndarray) -> np.ndarray:
        direction = np.sign(np.diff(closes))
        obv = np.concatenate([[0], np.cumsum(direction * vols[1:])])
        return obv

    @staticmethod
    def _vol_ratio(vols: np.ndarray, n: int) -> float:
        avg = float(np.mean(vols[-n - 1 : -1])) if len(vols) > n else 1.0
        cur = float(vols[-1])
        return float(np.clip(cur / (avg + 1e-9), 0, 10))
