"""
alchemy.services.price_stream
==============================
Real-time price streaming via Binance WebSocket.
Pushes live prices to all connected frontend clients.
Also snapshots equity curve data daily.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# ── Equity Curve Snapshots ────────────────────────────────────────────────────

EQUITY_DIR = Path("/data/equity_curves")
EQUITY_DIR.mkdir(parents=True, exist_ok=True)


def snapshot_equity(user_id: str, portfolio_value: float, cash: float,
                     unrealized_pnl: float, realized_pnl: float,
                     positions_count: int) -> None:
    """Save a single equity data point."""
    path = EQUITY_DIR / f"{user_id}.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "positions": positions_count,
    }
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_equity_curve(user_id: str, days: int = 30) -> list[dict]:
    """Read equity curve data points for a user."""
    path = EQUITY_DIR / f"{user_id}.jsonl"
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    points = []
    for line in open(path):
        try:
            d = json.loads(line.strip())
            ts = datetime.fromisoformat(d["ts"])
            if ts >= cutoff:
                points.append(d)
        except Exception:
            continue
    # Downsample: max 500 points
    if len(points) > 500:
        step = len(points) // 500
        points = points[::step]
    return points


# ── Binance WebSocket Price Stream ────────────────────────────────────────────

SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "bnbusdt", "xrpusdt", "dogeusdt", "adausdt"]

_latest_prices: dict[str, float] = {}
_ws_task: Optional[asyncio.Task] = None
_broadcast_fn = None
_last_equity_snapshot: float = 0  # epoch


def get_latest_prices() -> dict[str, float]:
    """Get latest cached prices from WebSocket stream."""
    return dict(_latest_prices)


async def start_price_stream(broadcast_fn=None, symbols: list[str] = None):
    """Start Binance WebSocket price stream."""
    global _ws_task, _broadcast_fn
    _broadcast_fn = broadcast_fn
    if _ws_task and not _ws_task.done():
        return

    syms = symbols or SYMBOLS
    _ws_task = asyncio.create_task(_run_ws(syms))
    log.info("price_stream.started", symbols=len(syms))


async def stop_price_stream():
    """Stop the WebSocket price stream."""
    global _ws_task
    if _ws_task:
        _ws_task.cancel()
        try:
            await _ws_task
        except asyncio.CancelledError:
            pass
        _ws_task = None
    log.info("price_stream.stopped")


async def _run_ws(symbols: list[str]):
    """Connect to Binance combined stream and push prices."""
    import websockets

    streams = "/".join(f"{s}@ticker" for s in symbols)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                log.info("price_stream.connected", url=url[:60])
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        payload = data.get("data", {})
                        symbol = payload.get("s", "").upper()  # e.g. BTCUSDT
                        price = float(payload.get("c", 0))     # last price
                        change_pct = float(payload.get("P", 0))  # 24h change %

                        if symbol and price > 0:
                            _latest_prices[symbol] = price

                            # Broadcast to frontend clients
                            if _broadcast_fn:
                                await _broadcast_fn("price_update", {
                                    "symbol": symbol,
                                    "price": price,
                                    "change_pct": round(change_pct, 2),
                                    "ts": int(time.time() * 1000),
                                })

                        # Equity snapshot every 5 minutes
                        await _maybe_snapshot_equity()

                    except (ValueError, KeyError):
                        continue

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("price_stream.reconnecting", error=str(e))
            await asyncio.sleep(5)


async def _maybe_snapshot_equity():
    """Snapshot equity curves every 5 minutes for all active users."""
    global _last_equity_snapshot
    now = time.time()
    if now - _last_equity_snapshot < 300:  # 5 minutes
        return
    _last_equity_snapshot = now

    try:
        from alchemy.paper_trading.engine import get_paper_engine
        engine = get_paper_engine()
        for uid, portfolio in engine._portfolios.items():
            snapshot_equity(
                user_id=uid,
                portfolio_value=portfolio.portfolio_value,
                cash=portfolio.cash_balance,
                unrealized_pnl=portfolio.total_unrealized_pnl,
                realized_pnl=portfolio.realized_pnl,
                positions_count=len(portfolio.positions),
            )
    except Exception as e:
        log.warning("equity_snapshot.failed", error=str(e))
