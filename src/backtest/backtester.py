"""
Backtesting Engine.

Runs the Alchemy signal pipeline on historical OHLCV data WITHOUT calling Claude,
using pure algorithmic signals:
  1. MarketForecaster  (ADX, LR, VWAP, regime)
  2. Technical rules   (RSI, MACD, Bollinger Bands)
  3. Optional: DerivativesSignalEngine (synthetic funding/OI)

Trade simulation:
  - Market-order entry (taker fee on notional)
  - Fixed SL / TP exits (or can use trailing)
  - Slippage model: fixed 0.02% per side
  - Max open positions respected
  - No pyramiding (one position per symbol at a time)

Output: BacktestResult with complete trade log + equity curve + PerformanceMetrics
"""

import math
import statistics
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from src.backtest.performance import PerformanceCalculator, PerformanceMetrics
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class BacktestTrade:
    """Single completed trade record from backtest."""

    symbol: str
    side: str  # "long" | "short"
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    size_usd: float
    leverage: int
    pnl_usd: float  # net after fees
    pnl_pct: float  # net % on margin
    fee_usd: float
    exit_reason: str  # "tp" | "sl" | "signal_exit" | "end_of_data"
    signal_score: float
    duration_bars: int

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_bar": self.entry_bar,
            "exit_bar": self.exit_bar,
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(self.exit_price, 6),
            "size_usd": round(self.size_usd, 2),
            "leverage": self.leverage,
            "pnl_usd": round(self.pnl_usd, 4),
            "pnl_pct": round(self.pnl_pct, 4),
            "fee_usd": round(self.fee_usd, 4),
            "exit_reason": self.exit_reason,
            "signal_score": round(self.signal_score, 4),
            "duration_bars": self.duration_bars,
        }


@dataclass
class BacktestResult:
    """Full output of one backtest run."""

    symbol: str
    timeframe: str
    total_bars: int
    initial_balance: float
    final_balance: float

    trades: List[BacktestTrade]
    equity_curve: List[float]  # portfolio value at each bar
    drawdown_curve: List[float]  # drawdown % at each bar

    metrics: PerformanceMetrics
    config_used: Dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_bars": self.total_bars,
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.final_balance, 2),
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": [round(v, 2) for v in self.equity_curve],
            "drawdown_curve": [round(v, 4) for v in self.drawdown_curve],
            "metrics": self.metrics.to_dict(),
            "config_used": self.config_used,
            "summary": self.metrics.summary(),
        }


# ── Backtesting Engine ────────────────────────────────────────────────────────


class BacktestEngine:
    """
    Runs the Alchemy trading strategy on historical OHLCV candles.
    No live API calls — everything is computed algorithmically.

    Signal generation pipeline:
      score = 0.4 × forecast_score + 0.35 × tech_score + 0.25 × vol_score
    """

    # Signal thresholds
    ENTRY_THRESHOLD = 0.25  # |score| must exceed this to generate signal
    MIN_ADX_TREND = 20.0  # below this = ranging regime
    MIN_CANDLES = 50  # minimum history for meaningful signals

    def __init__(self, config):
        self.config = config
        tc = config.trading
        self.taker = getattr(tc, "taker_fee_rate", 0.0005)
        self.maker = getattr(tc, "maker_fee_rate", 0.0002)
        self.leverage = getattr(tc, "leverage", 5)
        self.slippage = 0.0002  # 0.02% per side

    def run(
        self,
        candles: List[Dict],
        symbol: str = "BTCUSD",
        timeframe: str = "1h",
        initial_balance: float = 10_000.0,
        position_size_usd: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        leverage: Optional[int] = None,
        warmup_bars: int = 50,
    ) -> BacktestResult:
        """
        Run backtest on provided candles.

        Args:
            candles:          list of OHLCV dicts (close, open, high, low, volume)
            symbol:           symbol name (for labelling)
            timeframe:        candle timeframe string (for labelling)
            initial_balance:  starting portfolio value in USD
            position_size_usd: fixed margin per trade (default: 5% of initial balance)
            stop_loss_pct:    SL distance as % of entry (default: 2.0)
            take_profit_pct:  TP distance as % of entry (default: 4.5)
            leverage:         leverage multiplier (default: from config)
            warmup_bars:      bars to skip at start for indicator warm-up
        """
        lev = leverage or self.leverage
        sl_pct = (
            stop_loss_pct or getattr(self.config.trading, "stop_loss_pct", 2.0)
        ) / 100
        tp_pct = (
            take_profit_pct or getattr(self.config.trading, "take_profit_pct", 4.5)
        ) / 100
        pos_size = position_size_usd or initial_balance * 0.05

        from src.intelligence.market_forecaster import MarketForecaster

        forecaster = MarketForecaster(self.config)

        balance = initial_balance
        equity_curve = [balance]
        open_trade: Optional[BacktestTrade] = None
        completed: List[BacktestTrade] = []

        for i in range(warmup_bars, len(candles)):
            candle = candles[i]
            price = float(candle.get("close", 0))
            high = float(candle.get("high", price * 1.002))
            low = float(candle.get("low", price * 0.998))
            if price <= 0:
                equity_curve.append(balance)
                continue

            window = candles[max(0, i - 100) : i + 1]

            # ── Manage open trade ───────────────────────────────────────────
            if open_trade is not None:
                exit_price, exit_reason = self._check_exits(
                    open_trade, high, low, price, sl_pct, tp_pct
                )
                if exit_price is not None:
                    trade = self._close_trade(
                        open_trade, exit_price, i, exit_reason, lev
                    )
                    balance += trade.pnl_usd
                    completed.append(trade)
                    open_trade = None

            # ── Generate new signal ─────────────────────────────────────────
            if open_trade is None and balance > pos_size * 0.1:
                score, action = self._score(window, price, forecaster)
                if action in ("BUY", "SELL") and abs(score) >= self.ENTRY_THRESHOLD:
                    open_trade = self._open_trade(
                        symbol, action, price, i, pos_size, lev, score
                    )

            equity_curve.append(balance)

        # Close any remaining position at end of data
        if open_trade is not None:
            last_price = float(candles[-1].get("close", 0))
            if last_price > 0:
                trade = self._close_trade(
                    open_trade, last_price, len(candles) - 1, "end_of_data", lev
                )
                balance += trade.pnl_usd
                completed.append(trade)
        equity_curve[-1] = balance

        # ── Drawdown curve ────────────────────────────────────────────────
        peak = initial_balance
        dd_curve = []
        for v in equity_curve:
            peak = max(peak, v)
            dd_curve.append(round((peak - v) / peak * 100 if peak > 0 else 0, 4))

        # ── Performance metrics ───────────────────────────────────────────
        pnls_usd = [t.pnl_usd for t in completed]
        pnls_pct = [t.pnl_pct for t in completed]
        durs = [t.duration_bars for t in completed]

        calc = PerformanceCalculator()
        metrics = calc.calculate(
            equity_curve=equity_curve,
            trade_pnls_usd=pnls_usd,
            trade_pnls_pct=pnls_pct,
            trade_durations=durs,
            initial_balance=initial_balance,
            total_bars=len(candles),
        )

        cfg_used = {
            "symbol": symbol,
            "timeframe": timeframe,
            "initial_balance": initial_balance,
            "position_size_usd": pos_size,
            "stop_loss_pct": sl_pct * 100,
            "take_profit_pct": tp_pct * 100,
            "leverage": lev,
            "taker_fee_pct": self.taker * 100,
            "slippage_pct": self.slippage * 100,
            "warmup_bars": warmup_bars,
            "total_candles": len(candles),
        }

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            total_bars=len(candles),
            initial_balance=initial_balance,
            final_balance=balance,
            trades=completed,
            equity_curve=equity_curve,
            drawdown_curve=dd_curve,
            metrics=metrics,
            config_used=cfg_used,
        )

    # ── Signal generation ─────────────────────────────────────────────────────

    def _score(self, candles: List[Dict], price: float, forecaster) -> tuple:
        """Compute composite signal score without calling Claude."""
        if len(candles) < self.MIN_CANDLES:
            return 0.0, "HOLD"

        try:
            fc = forecaster.forecast(candles, price)
        except Exception:
            return 0.0, "HOLD"

        # Technical score from RSI + MACD + Bollinger
        tech_score = self._tech_score(candles, price)

        # Volume score
        vols = [float(c.get("volume", 1)) for c in candles[-20:]]
        avg_vol = statistics.mean(vols) if vols else 1
        recent_vol = vols[-1] if vols else avg_vol
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
        vol_score = min(0.3, (vol_ratio - 1.0) * 0.15)  # mild bonus for high volume

        composite = fc.forecast_score * 0.40 + tech_score * 0.35 + vol_score * 0.25
        composite = round(max(-1.0, min(1.0, composite)), 4)

        if composite >= self.ENTRY_THRESHOLD:
            return composite, "BUY"
        elif composite <= -self.ENTRY_THRESHOLD:
            return composite, "SELL"
        return composite, "HOLD"

    @staticmethod
    def _tech_score(candles: List[Dict], price: float) -> float:
        """Pure technical score in -1..+1 from RSI, MACD, Bollinger."""
        closes = [float(c.get("close", 0)) for c in candles]
        if len(closes) < 26:
            return 0.0

        # RSI (14)
        gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
        ag = statistics.mean(gains[-14:]) if len(gains) >= 14 else 0.0001
        al = statistics.mean(losses[-14:]) if len(losses) >= 14 else 0.0001
        rsi = 100 - (100 / (1 + ag / al)) if al > 0 else 50

        # MACD (12-26)
        def ema(data, n):
            k, e = 2 / (n + 1), data[0]
            for v in data[1:]:
                e = v * k + e * (1 - k)
            return e

        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd = ema12 - ema26

        # Bollinger (20, 2σ)
        sma20 = statistics.mean(closes[-20:])
        std20 = (
            statistics.stdev(closes[-20:]) if len(closes[-20:]) >= 2 else sma20 * 0.01
        )
        bb_pct = (price - (sma20 - 2 * std20)) / (4 * std20) if std20 > 0 else 0.5

        # Normalise to -1..+1
        rsi_score = (rsi - 50) / 50  # 0→−1, 100→+1
        macd_score = math.tanh(macd / (sma20 * 0.01)) if sma20 > 0 else 0.0
        bb_score = (bb_pct - 0.5) * 2  # 0→−1, 1→+1

        return round((rsi_score * 0.4 + macd_score * 0.4 + bb_score * 0.2), 4)

    # ── Trade management ──────────────────────────────────────────────────────

    def _open_trade(
        self, symbol, action, price, bar, size_usd, lev, score
    ) -> BacktestTrade:
        slip = price * self.slippage
        entry = price + slip if action == "BUY" else price - slip
        side = "long" if action == "BUY" else "short"
        fee = size_usd * lev * self.taker  # entry taker fee on notional

        return BacktestTrade(
            symbol=symbol,
            side=side,
            entry_bar=bar,
            exit_bar=-1,
            entry_price=entry,
            exit_price=0.0,
            size_usd=size_usd,
            leverage=lev,
            pnl_usd=-fee,  # open with fee deducted; will be updated on close
            pnl_pct=0.0,
            fee_usd=fee,
            exit_reason="open",
            signal_score=score,
            duration_bars=0,
        )

    def _close_trade(
        self, t: BacktestTrade, exit_price: float, bar: int, reason: str, lev: int
    ) -> BacktestTrade:
        slip = exit_price * self.slippage
        actual_exit = exit_price - slip if t.side == "long" else exit_price + slip

        if t.side == "long":
            gross_pnl = (actual_exit - t.entry_price) / t.entry_price * t.size_usd * lev
        else:
            gross_pnl = (t.entry_price - actual_exit) / t.entry_price * t.size_usd * lev

        exit_fee = t.size_usd * lev * self.taker
        total_fee = t.fee_usd + exit_fee
        net_pnl = gross_pnl - total_fee
        net_pct = net_pnl / t.size_usd * 100 if t.size_usd > 0 else 0.0

        t.exit_bar = bar
        t.exit_price = actual_exit
        t.pnl_usd = round(net_pnl, 6)
        t.pnl_pct = round(net_pct, 4)
        t.fee_usd = round(total_fee, 6)
        t.exit_reason = reason
        t.duration_bars = bar - t.entry_bar
        return t

    def _check_exits(
        self,
        t: BacktestTrade,
        high: float,
        low: float,
        close: float,
        sl_pct: float,
        tp_pct: float,
    ):
        """Return (exit_price, reason) or (None, None) if still open."""
        entry = t.entry_price
        if t.side == "long":
            sl_price = entry * (1 - sl_pct)
            tp_price = entry * (1 + tp_pct)
            if low <= sl_price:
                return sl_price, "sl"
            if high >= tp_price:
                return tp_price, "tp"
        else:
            sl_price = entry * (1 + sl_pct)
            tp_price = entry * (1 - tp_pct)
            if high >= sl_price:
                return sl_price, "sl"
            if low <= tp_price:
                return tp_price, "tp"
        return None, None
