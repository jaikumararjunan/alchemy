"""
ContractScanner — scans all Delta Exchange perpetual contracts,
scores each one using MarketForecaster + DerivativesSignalEngine,
and ranks them by opportunity quality.

Scoring:
  Forecast score  : 50 % (ADX trend, LR bias, VWAP position)
  Derivatives     : 30 % (funding, basis, OI conviction)
  Volatility bonus: 10 % (high ATR = bigger potential move)
  Volume bonus    : 10 % (OI + volume confirming the move)

Output: ranked list of ContractScore, top-N chosen for trading.
"""
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default watch-list of perpetual symbols on Delta Exchange India
DEFAULT_WATCH_LIST = [
    "BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD",
    "AVAXUSD", "DOGEUSD", "MATICUSD", "LINKUSD", "DOTUSD",
    "ADAUSD", "LTCUSD", "ATOMUSD", "NEARUSD", "APTUSD",
]


@dataclass
class ContractScore:
    """Score and metadata for a single contract scan."""
    symbol: str
    rank: int
    composite_score: float          # -1.0 to +1.0
    action: str                     # "BUY" | "SELL" | "HOLD"
    confidence: float               # 0.0 – 1.0

    current_price: float
    change_24h_pct: float
    volume_24h: float
    open_interest: float

    # Sub-scores
    forecast_score: float
    derivatives_score: float
    volatility_score: float
    volume_score: float

    # Technical details
    adx: float
    market_regime: str              # "trending" | "ranging" | "volatile"
    trend_direction: str            # "bullish" | "bearish" | "neutral"
    forecast_bias: str
    regression_r2: float
    breakeven_move_pct: float

    # Risk / opportunity
    expected_move_pct: float        # abs projected 3-bar move
    risk_reward_estimate: float     # rough R:R before entry sizing
    scan_time_ms: float

    # Allocation suggestion
    suggested_size_pct: float       # % of available capital to allocate
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rank": self.rank,
            "composite_score": round(self.composite_score, 4),
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "current_price": round(self.current_price, 4),
            "change_24h_pct": round(self.change_24h_pct, 3),
            "volume_24h": round(self.volume_24h, 2),
            "open_interest": round(self.open_interest, 2),
            "forecast_score": round(self.forecast_score, 4),
            "derivatives_score": round(self.derivatives_score, 4),
            "volatility_score": round(self.volatility_score, 4),
            "volume_score": round(self.volume_score, 4),
            "adx": round(self.adx, 2),
            "market_regime": self.market_regime,
            "trend_direction": self.trend_direction,
            "forecast_bias": self.forecast_bias,
            "regression_r2": round(self.regression_r2, 4),
            "breakeven_move_pct": round(self.breakeven_move_pct, 3),
            "expected_move_pct": round(self.expected_move_pct, 3),
            "risk_reward_estimate": round(self.risk_reward_estimate, 2),
            "suggested_size_pct": round(self.suggested_size_pct, 1),
            "scan_time_ms": round(self.scan_time_ms, 1),
            "reasoning": self.reasoning,
        }


@dataclass
class ScanResult:
    """Result of a full multi-contract scan."""
    ranked_contracts: List[ContractScore]
    top_opportunities: List[ContractScore]   # filtered: actionable + high confidence
    scan_timestamp: str
    total_scanned: int
    total_actionable: int
    scan_duration_seconds: float
    market_summary: str              # one-line headline

    def to_dict(self) -> dict:
        return {
            "ranked_contracts": [c.to_dict() for c in self.ranked_contracts],
            "top_opportunities": [c.to_dict() for c in self.top_opportunities],
            "scan_timestamp": self.scan_timestamp,
            "total_scanned": self.total_scanned,
            "total_actionable": self.total_actionable,
            "scan_duration_seconds": round(self.scan_duration_seconds, 2),
            "market_summary": self.market_summary,
        }


class ContractScanner:
    """
    Scans multiple contracts and ranks them by opportunity quality.
    Designed to work in both dry-run (synthetic data) and live modes.
    """

    _W_FORECAST    = 0.50
    _W_DERIVATIVES = 0.30
    _W_VOLATILITY  = 0.10
    _W_VOLUME      = 0.10

    _MIN_CONFIDENCE = 0.45
    _MIN_ADX_FOR_TREND = 20.0

    def __init__(self, config, exchange=None, max_workers: int = 6):
        self.config    = config
        self.exchange  = exchange
        self.max_workers = max_workers
        tc = config.trading
        self.taker_fee = getattr(tc, "taker_fee_rate", 0.0005)
        self.leverage  = getattr(tc, "leverage", 5)

    # ── Public API ────────────────────────────────────────────────────────────

    def scan(self, symbols: Optional[List[str]] = None) -> ScanResult:
        """
        Scan all given symbols (or DEFAULT_WATCH_LIST) and return ranked results.
        Uses a thread pool so multiple symbols are scored concurrently.
        """
        symbols = symbols or DEFAULT_WATCH_LIST
        start = time.time()
        scores: List[ContractScore] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._score_symbol, sym): sym for sym in symbols}
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    score = fut.result(timeout=30)
                    if score:
                        scores.append(score)
                except Exception as e:
                    logger.warning(f"Scan failed for {sym}: {e}")

        # Sort by abs(composite_score) * confidence (best opportunity first)
        scores.sort(key=lambda s: abs(s.composite_score) * s.confidence, reverse=True)
        for i, s in enumerate(scores):
            s.rank = i + 1

        # Top opportunities: actionable + confidence threshold
        top = [s for s in scores
               if s.action in ("BUY", "SELL") and s.confidence >= self._MIN_CONFIDENCE][:5]

        # Capital allocation suggestion across top picks
        self._assign_allocations(top)

        elapsed = time.time() - start
        actionable = sum(1 for s in scores if s.action != "HOLD")

        summary = self._build_summary(scores, top)

        return ScanResult(
            ranked_contracts=scores,
            top_opportunities=top,
            scan_timestamp=datetime.now(timezone.utc).isoformat(),
            total_scanned=len(scores),
            total_actionable=actionable,
            scan_duration_seconds=elapsed,
            market_summary=summary,
        )

    # ── Private: score one symbol ─────────────────────────────────────────────

    def _score_symbol(self, symbol: str) -> Optional[ContractScore]:
        t0 = time.time()
        try:
            candles, ticker = self._fetch_data(symbol)
            if not candles or len(candles) < 30:
                return None

            price  = ticker["mark_price"]
            vol24  = ticker["volume_24h"]
            chg24  = ticker["change_24h_pct"]
            oi     = ticker["open_interest"]

            # ── Forecast score ───────────────────────────────────────────────
            from src.intelligence.market_forecaster import MarketForecaster
            forecaster = MarketForecaster(self.config)
            fc = forecaster.forecast(candles, price)
            forecast_score = fc.forecast_score  # -1 to +1

            # ── Derivatives score ────────────────────────────────────────────
            deriv_score = 0.0
            try:
                from src.derivatives.derivatives_signal import DerivativesSignalEngine
                engine = DerivativesSignalEngine()
                funding = ticker.get("funding_rate", random.gauss(0.0001, 0.0003))
                ds = engine.analyze(
                    current_price=price,
                    funding_rate=funding,
                    spot_price=price * 0.9997,
                    open_interest=oi,
                )
                deriv_score = ds.composite_score
            except Exception:
                pass

            # ── Volatility score (ATR proxy) ─────────────────────────────────
            closes = [float(c.get("close", 0)) for c in candles[-20:]]
            highs  = [float(c.get("high", closes[i] * 1.002)) for i, c in enumerate(candles[-20:])]
            lows   = [float(c.get("low",  closes[i] * 0.998)) for i, c in enumerate(candles[-20:])]
            tr_list = [highs[i] - lows[i] for i in range(len(closes))]
            atr = sum(tr_list) / len(tr_list) if tr_list else price * 0.01
            atr_pct = atr / price * 100
            # Ideal ATR: 1-4% for a good move. Below 0.5% = dead; above 6% = too risky
            if atr_pct < 0.5:
                vol_score = -0.3
            elif atr_pct > 6.0:
                vol_score = -0.2
            else:
                vol_score = min(1.0, atr_pct / 3.0) * 0.8

            # ── Volume score ─────────────────────────────────────────────────
            vols = [float(c.get("volume", 0)) for c in candles[-20:]]
            avg_vol = sum(vols) / len(vols) if vols else 1
            recent_vol = sum(vols[-3:]) / 3 if len(vols) >= 3 else avg_vol
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
            # Volume rising and large OI = higher conviction
            oi_norm = min(1.0, oi / 500_000_000)  # normalise to $500M
            vol_score_component = min(1.0, (vol_ratio - 1.0) * 0.5 + oi_norm * 0.5)

            # ── Composite ────────────────────────────────────────────────────
            composite = (
                forecast_score    * self._W_FORECAST    +
                deriv_score       * self._W_DERIVATIVES +
                vol_score         * self._W_VOLATILITY  +
                vol_score_component * self._W_VOLUME
            )
            composite = round(max(-1.0, min(1.0, composite)), 4)

            # Confidence: how coherent are sub-signals?
            sub = [forecast_score, deriv_score]
            agree = sum(1 for s in sub if (s > 0) == (composite > 0))
            confidence = round(agree / len(sub) * 0.6 + abs(composite) * 0.4, 3)
            confidence = min(1.0, confidence)

            # Action
            if composite >= 0.20 and confidence >= self._MIN_CONFIDENCE:
                action = "BUY"
            elif composite <= -0.20 and confidence >= self._MIN_CONFIDENCE:
                action = "SELL"
            else:
                action = "HOLD"

            # Expected move (3-bar LR projection vs current)
            expected_move = 0.0
            if fc.forecast_price_3 and price > 0:
                expected_move = abs(fc.forecast_price_3 - price) / price * 100

            # Rough R:R estimate
            rt_fee_pct = self.taker_fee * 2 * self.leverage * 100
            net_move = expected_move - rt_fee_pct
            rr_estimate = net_move / (atr_pct * 0.5) if atr_pct > 0 else 0.0

            # Reasoning
            reasons = [
                f"ADX {fc.adx:.1f} ({fc.market_regime})",
                f"trend {fc.trend_direction}",
                f"forecast {fc.forecast_bias}",
            ]
            if fc.regression_r2 > 0.4:
                reasons.append(f"R²={fc.regression_r2:.2f}")
            if abs(deriv_score) > 0.2:
                reasons.append(f"deriv {deriv_score:+.2f}")
            reasoning = " | ".join(reasons)

            elapsed_ms = (time.time() - t0) * 1000
            return ContractScore(
                symbol=symbol, rank=0,
                composite_score=composite, action=action, confidence=confidence,
                current_price=price, change_24h_pct=chg24, volume_24h=vol24, open_interest=oi,
                forecast_score=round(forecast_score, 4), derivatives_score=round(deriv_score, 4),
                volatility_score=round(vol_score, 4), volume_score=round(vol_score_component, 4),
                adx=fc.adx, market_regime=fc.market_regime, trend_direction=fc.trend_direction,
                forecast_bias=fc.forecast_bias, regression_r2=fc.regression_r2,
                breakeven_move_pct=fc.breakeven_move_pct,
                expected_move_pct=round(expected_move, 3),
                risk_reward_estimate=round(rr_estimate, 2),
                suggested_size_pct=0.0,   # filled in _assign_allocations
                scan_time_ms=elapsed_ms,
                reasoning=reasoning,
            )
        except Exception as e:
            logger.warning(f"_score_symbol({symbol}) error: {e}")
            return None

    # ── Private: data fetch ───────────────────────────────────────────────────

    def _fetch_data(self, symbol: str) -> tuple:
        """Return (candles, ticker_dict) for the symbol."""
        if not self.config.trading.dry_run and self.exchange:
            try:
                end_t = int(time.time())
                candles = self.exchange.get_candles(
                    symbol, resolution=3600, start=end_t - 3600 * 100, end=end_t
                )
                ticker = self.exchange.get_ticker(symbol)
                ticker_dict = {
                    "mark_price": ticker.mark_price,
                    "volume_24h": ticker.volume_24h,
                    "change_24h_pct": ticker.change_24h_pct,
                    "open_interest": ticker.open_interest,
                    "funding_rate": 0.0001,
                }
                return candles, ticker_dict
            except Exception as e:
                logger.warning(f"Live fetch failed for {symbol}: {e}")

        # Dry-run: generate deterministic-ish synthetic data
        return self._synthetic_data(symbol)

    def _synthetic_data(self, symbol: str) -> tuple:
        """Generate synthetic OHLCV + ticker for dry-run / offline testing."""
        rng = random.Random(hash(symbol) % (2**31))
        base_prices = {
            "BTCUSD": 67000, "ETHUSD": 3500, "SOLUSD": 185, "BNBUSD": 420,
            "XRPUSD": 0.62, "AVAXUSD": 38, "DOGEUSD": 0.17, "MATICUSD": 0.95,
            "LINKUSD": 18, "DOTUSD": 9.5, "ADAUSD": 0.55, "LTCUSD": 95,
            "ATOMUSD": 10.5, "NEARUSD": 7.2, "APTUSD": 12.0,
        }
        base = base_prices.get(symbol, 50.0)
        vol_multi = base_prices.get(symbol, 50.0) / 50.0
        candles = []
        for i in range(100):
            trend = 0.4 * math.sin(i / 12) + rng.gauss(0, 0.008) * base
            c = base + trend
            h = c + abs(rng.gauss(0, base * 0.006))
            lo = c - abs(rng.gauss(0, base * 0.006))
            candles.append({
                "close": round(c, 6), "open": round(c + rng.gauss(0, base * 0.003), 6),
                "high": round(h, 6), "low": round(lo, 6),
                "volume": round(abs(rng.gauss(200, 80)) * vol_multi, 2),
            })
        ticker = {
            "mark_price": candles[-1]["close"],
            "volume_24h": round(abs(rng.gauss(15000, 4000)) * vol_multi, 2),
            "change_24h_pct": round(rng.gauss(0, 3.5), 3),
            "open_interest": round(abs(rng.gauss(500e6, 150e6)) * (base / 1000), 2),
            "funding_rate": round(rng.gauss(0.0001, 0.0006), 6),
        }
        return candles, ticker

    # ── Private: helpers ──────────────────────────────────────────────────────

    def _assign_allocations(self, top: List[ContractScore]) -> None:
        """Distribute capital proportionally across top opportunities by |score|."""
        if not top:
            return
        weights = [abs(s.composite_score) * s.confidence for s in top]
        total = sum(weights) or 1.0
        for s, w in zip(top, weights):
            s.suggested_size_pct = round(w / total * 100, 1)

    def _build_summary(self, all_scores: List[ContractScore],
                        top: List[ContractScore]) -> str:
        if not all_scores:
            return "No contracts scanned."
        buy_cnt  = sum(1 for s in all_scores if s.action == "BUY")
        sell_cnt = sum(1 for s in all_scores if s.action == "SELL")
        trending = [s.symbol for s in all_scores[:5] if s.market_regime == "trending"]
        parts = [f"Scanned {len(all_scores)} contracts: {buy_cnt} BUY / {sell_cnt} SELL signals."]
        if top:
            top_str = ", ".join(f"{s.symbol}({s.action})" for s in top[:3])
            parts.append(f"Top opportunities: {top_str}.")
        if trending:
            parts.append(f"Trending: {', '.join(trending[:3])}.")
        return " ".join(parts)

    # ── Convenience: get just tradeable perpetuals from exchange ─────────────

    def get_tradeable_symbols(self) -> List[str]:
        """Return all perpetual symbols available on the exchange."""
        if not self.exchange or self.config.trading.dry_run:
            return DEFAULT_WATCH_LIST
        try:
            products = self.exchange.get_products()
            return [
                p["symbol"] for p in products
                if p.get("contract_type") in ("perpetual_futures",)
                and p.get("is_active", False)
                and p.get("quoting_asset", {}).get("symbol") == "USD"
            ]
        except Exception as e:
            logger.warning(f"get_tradeable_symbols failed: {e}")
            return DEFAULT_WATCH_LIST
