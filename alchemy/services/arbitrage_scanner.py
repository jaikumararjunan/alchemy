"""
alchemy.services.arbitrage_scanner
=====================================
Multi-exchange arbitrage opportunity scanner.

Scans price differences across Binance, Delta Exchange (and extendable to
Kite, Angel, etc.) for the same asset to detect arbitrage windows.

Features:
  - Real-time price comparison across exchanges
  - Spread calculation (absolute + percentage)
  - Fee-adjusted profitability check
  - Historical spread tracking
  - Alert generation for opportunities above threshold
  - Support for spot, perpetual futures, and cross-type arb
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import structlog
log = structlog.get_logger(__name__)


@dataclass
class PriceQuote:
    """Price from a single exchange."""
    exchange: str
    symbol: str
    bid: float = 0
    ask: float = 0
    mid: float = 0
    last: float = 0
    volume_24h: float = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.mid and self.bid and self.ask:
            self.mid = (self.bid + self.ask) / 2
        if not self.mid and self.last:
            self.mid = self.last
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_usd: float
    spread_pct: float
    estimated_fee_pct: float = 0.2  # Total round-trip fee estimate
    net_profit_pct: float = 0
    profitable: bool = False
    volume_ok: bool = True
    timestamp: str = ""

    def __post_init__(self):
        self.net_profit_pct = round(self.spread_pct - self.estimated_fee_pct, 4)
        self.profitable = self.net_profit_pct > 0
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── Exchange price fetchers ───────────────────────────────────────────────────

async def _fetch_binance_prices(symbols: list[str]) -> list[PriceQuote]:
    """Fetch prices from Binance."""
    quotes = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/bookTicker")
            if r.status_code == 200:
                data = {d["symbol"]: d for d in r.json()}
                for sym in symbols:
                    bsym = sym.replace("/", "").replace("-", "").upper()
                    if bsym in data:
                        d = data[bsym]
                        quotes.append(PriceQuote(
                            exchange="binance", symbol=sym,
                            bid=float(d["bidPrice"]), ask=float(d["askPrice"]),
                        ))
    except Exception as e:
        log.warning("arb.binance_fetch_failed", error=str(e))
    return quotes


async def _fetch_delta_prices(symbols: list[str]) -> list[PriceQuote]:
    """Fetch prices from Delta Exchange."""
    quotes = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://api.delta.exchange/v2/tickers")
            if r.status_code == 200:
                data = {d["symbol"]: d for d in r.json().get("result", [])}
                for sym in symbols:
                    dsym = sym.replace("/", "").replace("-", "").upper()
                    # Try common Delta naming conventions
                    for candidate in [dsym, f"{dsym}PERP", dsym.replace("USDT", "USD")]:
                        if candidate in data:
                            d = data[candidate]
                            quotes.append(PriceQuote(
                                exchange="delta", symbol=sym,
                                bid=float(d.get("best_bid", 0) or 0),
                                ask=float(d.get("best_ask", 0) or 0),
                                last=float(d.get("close", 0) or d.get("mark_price", 0) or 0),
                                volume_24h=float(d.get("turnover_usd", 0) or 0),
                            ))
                            break
    except Exception as e:
        log.warning("arb.delta_fetch_failed", error=str(e))
    return quotes


async def _fetch_coingecko_prices(symbols: list[str]) -> list[PriceQuote]:
    """Fetch spot prices from CoinGecko as reference."""
    quotes = []
    id_map = {
        "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
        "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
        "ADAUSDT": "cardano", "AVAXUSDT": "avalanche-2",
    }
    ids = []
    for sym in symbols:
        clean = sym.replace("/", "").replace("-", "").upper()
        if clean in id_map:
            ids.append(id_map[clean])
    if not ids:
        return quotes
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.coingecko.com/api/v3/simple/price",
                                  params={"ids": ",".join(ids), "vs_currencies": "usd"})
            if r.status_code == 200:
                data = r.json()
                for sym in symbols:
                    clean = sym.replace("/", "").replace("-", "").upper()
                    cg_id = id_map.get(clean, "")
                    if cg_id in data:
                        price = data[cg_id]["usd"]
                        quotes.append(PriceQuote(
                            exchange="coingecko_spot", symbol=sym,
                            mid=price, last=price,
                        ))
    except Exception as e:
        log.warning("arb.coingecko_fetch_failed", error=str(e))
    return quotes


# ── Scanner ───────────────────────────────────────────────────────────────────

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]

# Fee estimates (maker+taker round-trip per exchange pair)
FEE_ESTIMATES = {
    ("binance", "delta"): 0.15,        # ~0.075% each side
    ("binance", "coingecko_spot"): 0.1, # Binance vs spot reference
    ("delta", "coingecko_spot"): 0.15,
}


async def scan_arbitrage(
    symbols: list[str] = None,
    min_spread_pct: float = 0.05,
    include_coingecko: bool = True,
) -> dict:
    """
    Scan for arbitrage opportunities across exchanges.

    Returns:
        dict with 'opportunities', 'prices', 'scan_time'
    """
    symbols = symbols or DEFAULT_SYMBOLS
    start = time.time()

    # Fetch prices concurrently
    tasks = [
        _fetch_binance_prices(symbols),
        _fetch_delta_prices(symbols),
    ]
    if include_coingecko:
        tasks.append(_fetch_coingecko_prices(symbols))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate by symbol
    prices_by_symbol: dict[str, list[PriceQuote]] = {}
    all_quotes = []
    for result in results:
        if isinstance(result, Exception):
            continue
        for q in result:
            if q.mid > 0 or q.last > 0:
                prices_by_symbol.setdefault(q.symbol, []).append(q)
                all_quotes.append(asdict(q))

    # Find opportunities
    opportunities = []
    for symbol, quotes in prices_by_symbol.items():
        if len(quotes) < 2:
            continue
        for i, q1 in enumerate(quotes):
            for q2 in quotes[i+1:]:
                p1 = q1.ask if q1.ask > 0 else q1.mid or q1.last
                p2 = q2.bid if q2.bid > 0 else q2.mid or q2.last
                p1_buy = q1.ask if q1.ask > 0 else q1.mid or q1.last
                p2_buy = q2.ask if q2.ask > 0 else q2.mid or q2.last
                p1_sell = q1.bid if q1.bid > 0 else q1.mid or q1.last
                p2_sell = q2.bid if q2.bid > 0 else q2.mid or q2.last

                # Check both directions
                for buy_ex, buy_p, sell_ex, sell_p in [
                    (q1.exchange, p1_buy, q2.exchange, p2_sell),
                    (q2.exchange, p2_buy, q1.exchange, p1_sell),
                ]:
                    if buy_p <= 0 or sell_p <= 0:
                        continue
                    spread = sell_p - buy_p
                    spread_pct = (spread / buy_p) * 100
                    if spread_pct >= min_spread_pct:
                        fee_key = tuple(sorted([buy_ex, sell_ex]))
                        fee = FEE_ESTIMATES.get(fee_key, 0.2)
                        opp = ArbitrageOpportunity(
                            symbol=symbol,
                            buy_exchange=buy_ex, sell_exchange=sell_ex,
                            buy_price=round(buy_p, 6), sell_price=round(sell_p, 6),
                            spread_usd=round(spread, 4),
                            spread_pct=round(spread_pct, 4),
                            estimated_fee_pct=fee,
                        )
                        opportunities.append(asdict(opp))

    # Sort by net profit
    opportunities.sort(key=lambda x: x["net_profit_pct"], reverse=True)

    scan_time = round(time.time() - start, 2)
    log.info("arb.scan_complete", symbols=len(symbols), quotes=len(all_quotes),
             opportunities=len(opportunities), seconds=scan_time)

    return {
        "opportunities": opportunities,
        "profitable": [o for o in opportunities if o["profitable"]],
        "prices": all_quotes,
        "symbols_scanned": len(symbols),
        "exchanges_reached": len(set(q["exchange"] for q in all_quotes)),
        "scan_time_seconds": scan_time,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
