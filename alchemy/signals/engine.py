"""
alchemy.signals — AI Signal Generator + News Sentiment + Custom Indicators
===========================================================================
Features 5, 10, 18 from the roadmap.
"""
from __future__ import annotations
import math, time, hashlib, json, os
from datetime import datetime, timezone
from typing import Optional
import structlog

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Feature 5: AI Signal Generator
# ══════════════════════════════════════════════════════════════════════════════

class Signal:
    def __init__(self, symbol, direction, confidence, strategy, price, **kw):
        self.id = hashlib.md5(f"{symbol}{direction}{time.time()}".encode()).hexdigest()[:10]
        self.symbol = symbol
        self.direction = direction  # "long", "short", "neutral"
        self.confidence = confidence  # 0.0 - 1.0
        self.strategy = strategy
        self.price = price
        self.entry = kw.get("entry", price)
        self.stop_loss = kw.get("stop_loss", 0)
        self.take_profit = kw.get("take_profit", 0)
        self.timeframe = kw.get("timeframe", "1h")
        self.reasoning = kw.get("reasoning", "")
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status = "active"  # active, filled, expired, cancelled

    def to_dict(self):
        return self.__dict__.copy()


def generate_signals(candles: list[dict], symbol: str = "BTCUSDT") -> list[Signal]:
    """
    Generate trading signals using multiple indicator confluence.
    Combines: SMA crossover, RSI, MACD, volume analysis.
    Returns signals with confidence scores (0-1).
    """
    if len(candles) < 50:
        return []

    closes = [c["close"] for c in candles]
    volumes = [c.get("volume", 0) for c in candles]
    signals = []

    # Calculate indicators
    sma9 = _sma(closes, 9)
    sma21 = _sma(closes, 21)
    sma50 = _sma(closes, 50)
    rsi = _rsi(closes, 14)
    macd_line, signal_line = _macd(closes)
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1

    i = len(candles) - 1
    if not all([sma9[i], sma21[i], sma50[i], rsi[i], macd_line[i], signal_line[i]]):
        return []

    price = closes[i]
    score = 0
    reasons = []

    # SMA Trend
    if sma9[i] > sma21[i] > sma50[i]:
        score += 0.25; reasons.append("Uptrend: SMA9 > SMA21 > SMA50")
    elif sma9[i] < sma21[i] < sma50[i]:
        score -= 0.25; reasons.append("Downtrend: SMA9 < SMA21 < SMA50")

    # SMA Crossover
    if sma9[i-1] <= sma21[i-1] and sma9[i] > sma21[i]:
        score += 0.2; reasons.append("Bullish SMA crossover")
    elif sma9[i-1] >= sma21[i-1] and sma9[i] < sma21[i]:
        score -= 0.2; reasons.append("Bearish SMA crossover")

    # RSI
    if rsi[i] < 30:
        score += 0.2; reasons.append(f"RSI oversold: {rsi[i]:.1f}")
    elif rsi[i] > 70:
        score -= 0.2; reasons.append(f"RSI overbought: {rsi[i]:.1f}")
    elif 40 < rsi[i] < 60:
        reasons.append(f"RSI neutral: {rsi[i]:.1f}")

    # MACD
    if macd_line[i] > signal_line[i] and macd_line[i-1] <= signal_line[i-1]:
        score += 0.2; reasons.append("MACD bullish crossover")
    elif macd_line[i] < signal_line[i] and macd_line[i-1] >= signal_line[i-1]:
        score -= 0.2; reasons.append("MACD bearish crossover")

    # Volume confirmation
    if volumes[i] > avg_vol * 1.5:
        score *= 1.15; reasons.append("High volume confirmation")

    confidence = min(abs(score), 1.0)
    if confidence >= 0.3:
        direction = "long" if score > 0 else "short"
        sl = price * (0.98 if direction == "long" else 1.02)
        tp = price * (1.04 if direction == "long" else 0.96)

        signals.append(Signal(
            symbol=symbol, direction=direction, confidence=round(confidence, 3),
            strategy="ai_confluence", price=price,
            entry=price, stop_loss=round(sl, 2), take_profit=round(tp, 2),
            timeframe="1h", reasoning=" | ".join(reasons),
        ))

    return signals


# ══════════════════════════════════════════════════════════════════════════════
# Feature 10: News & Sentiment Feed
# ══════════════════════════════════════════════════════════════════════════════

class SentimentResult:
    def __init__(self, symbol, score, label, headline, source, url=""):
        self.symbol = symbol
        self.score = score          # -1.0 to 1.0
        self.label = label          # "bullish", "bearish", "neutral"
        self.headline = headline
        self.source = source
        self.url = url
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return self.__dict__.copy()


async def fetch_crypto_sentiment(symbol: str = "BTC") -> list[dict]:
    """Fetch crypto news and analyze sentiment using keyword scoring."""
    import httpx

    sentiments = []
    try:
        # Use CryptoCompare news API (free, no key required for basic)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/v2/news/",
                params={"lang": "EN", "categories": symbol}
            )
            data = resp.json()
            articles = data.get("Data", [])[:20]

            for article in articles:
                title = article.get("title", "")
                body = article.get("body", "")[:200]
                score = _simple_sentiment(title + " " + body)
                label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"

                sentiments.append(SentimentResult(
                    symbol=symbol, score=round(score, 3), label=label,
                    headline=title, source=article.get("source", ""),
                    url=article.get("url", ""),
                ).to_dict())

    except Exception as e:
        log.warning("sentiment.fetch_error", error=str(e))

    return sentiments


def _simple_sentiment(text: str) -> float:
    """Simple keyword-based sentiment (-1 to 1)."""
    text = text.lower()
    bull = ["surge","rally","bullish","gains","soar","breakthrough","all-time high",
            "adoption","growth","positive","upgrade","buy","moon","pump","recover"]
    bear = ["crash","plunge","bearish","dump","sell-off","decline","drop","fear",
            "hack","ban","regulation","fine","fraud","warning","risk","loss"]
    bull_count = sum(1 for w in bull if w in text)
    bear_count = sum(1 for w in bear if w in text)
    total = bull_count + bear_count
    if total == 0: return 0.0
    return (bull_count - bear_count) / total


def get_market_sentiment_summary(sentiments: list[dict]) -> dict:
    """Aggregate sentiment across multiple articles."""
    if not sentiments:
        return {"overall": "neutral", "score": 0, "count": 0}
    scores = [s["score"] for s in sentiments]
    avg = sum(scores) / len(scores)
    label = "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral"
    return {
        "overall": label, "score": round(avg, 3),
        "count": len(sentiments),
        "bullish": len([s for s in scores if s > 0.15]),
        "bearish": len([s for s in scores if s < -0.15]),
        "neutral": len([s for s in scores if -0.15 <= s <= 0.15]),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 18: Custom Indicator Builder
# ══════════════════════════════════════════════════════════════════════════════

BUILTIN_INDICATORS = {
    "sma":  lambda data, p: _sma(data, p),
    "ema":  lambda data, p: _ema(data, p),
    "rsi":  lambda data, p: _rsi(data, p),
    "macd": lambda data, _: _macd(data),
    "bb":   lambda data, p: _bb(data, p),
    "atr":  lambda data, p: _atr(data, p),
    "vwap": lambda data, _: _vwap(data),
}

class CustomIndicator:
    def __init__(self, name, formula, params=None):
        self.id = str(hash(name))[:8]
        self.name = name
        self.formula = formula  # e.g., "ema(close, 20) - ema(close, 50)"
        self.params = params or {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def calculate(self, candles):
        """Evaluate the custom indicator formula on candle data."""
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c.get("volume", 0) for c in candles]

        # Safe evaluation context
        ctx = {
            "close": closes, "high": highs, "low": lows, "volume": volumes,
            "sma": lambda d, p: _sma(d, p),
            "ema": lambda d, p: _ema(d, p),
            "rsi": lambda d, p: _rsi(d, p),
            "abs": abs, "max": max, "min": min, "len": len,
        }
        try:
            result = eval(self.formula, {"__builtins__": {}}, ctx)
            return {"name": self.name, "values": result, "success": True}
        except Exception as e:
            return {"name": self.name, "error": str(e), "success": False}

    def to_dict(self):
        return {"id": self.id, "name": self.name, "formula": self.formula,
                "params": self.params, "created_at": self.created_at}


_custom_indicators: dict[str, list[CustomIndicator]] = {}

def add_custom_indicator(user_id, name, formula, params=None):
    ci = CustomIndicator(name, formula, params)
    _custom_indicators.setdefault(user_id, []).append(ci)
    return ci.to_dict()

def get_custom_indicators(user_id):
    return [ci.to_dict() for ci in _custom_indicators.get(user_id, [])]


# ── Shared indicator calculations ─────────────────────────────────────────────

def _sma(data, period):
    r = [None] * len(data)
    for i in range(period - 1, len(data)):
        r[i] = sum(data[i - period + 1:i + 1]) / period
    return r

def _ema(data, period):
    r = [None] * len(data)
    k = 2 / (period + 1)
    r[0] = data[0]
    for i in range(1, len(data)):
        prev = r[i-1] if r[i-1] is not None else data[i]
        r[i] = data[i] * k + prev * (1 - k)
    return r

def _rsi(data, period=14):
    r = [None] * len(data)
    if len(data) < period + 1: return r
    gains, losses = [], []
    for i in range(1, period + 1):
        d = data[i] - data[i-1]
        gains.append(max(0, d)); losses.append(max(0, -d))
    ag = sum(gains)/period; al = sum(losses)/period
    r[period] = 100 if al == 0 else 100 - 100/(1 + ag/al)
    for i in range(period+1, len(data)):
        d = data[i] - data[i-1]
        ag = (ag*(period-1) + max(0,d))/period
        al = (al*(period-1) + max(0,-d))/period
        r[i] = 100 if al == 0 else 100 - 100/(1 + ag/al)
    return r

def _macd(data, fast=12, slow=26, signal=9):
    ema_fast = _ema(data, fast)
    ema_slow = _ema(data, slow)
    macd = [None if f is None or s is None else f - s for f, s in zip(ema_fast, ema_slow)]
    valid = [m for m in macd if m is not None]
    sig = _ema(valid, signal) if len(valid) >= signal else [None]*len(valid)
    # Pad signal to match length
    sig_full = [None]*(len(macd)-len(sig)) + sig
    return macd, sig_full

def _bb(data, period=20, mult=2.0):
    sma = _sma(data, period)
    upper, lower = [None]*len(data), [None]*len(data)
    for i in range(period-1, len(data)):
        if sma[i] is None: continue
        w = data[i-period+1:i+1]
        std = math.sqrt(sum((x-sma[i])**2 for x in w)/period)
        upper[i] = sma[i] + mult*std
        lower[i] = sma[i] - mult*std
    return {"upper": upper, "lower": lower, "mid": sma}

def _atr(candles, period=14):
    if isinstance(candles[0], (int, float)):
        return [None]*len(candles)  # Need OHLC
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    result = [None]*(period+1)
    if len(trs) >= period:
        result.append(sum(trs[:period])/period)
        for i in range(period, len(trs)):
            result.append((result[-1]*(period-1) + trs[i])/period)
    return result

def _vwap(candles):
    cum_vol = 0; cum_tp_vol = 0; result = []
    for c in candles:
        tp = (c["high"] + c["low"] + c["close"]) / 3
        v = c.get("volume", 0)
        cum_vol += v; cum_tp_vol += tp * v
        result.append(cum_tp_vol / cum_vol if cum_vol > 0 else tp)
    return result
