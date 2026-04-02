"""
alchemy.workflows.smart_router
================================
Smart Order Router — selects the best exchange for each order.

Routing factors:
  1. Asset availability (does exchange list this symbol?)
  2. Token validity (is the exchange token active and valid?)
  3. Liquidity score (bid-ask spread + order book depth)
  4. Fee comparison (taker fee per exchange)
  5. Paper mode (route to preferred paper exchange)
  6. Manual override (request.exchange != "auto")

Usage::

    router = SmartRouter(token_manager)
    decision = await router.route(request)
    print(decision.exchange, decision.reason)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import structlog

from alchemy.tokens.manager import TokenManager
from alchemy.tokens.models import ExchangeID
from alchemy.workflows.states import OrderRequest, OrderSide

log = structlog.get_logger(__name__)

# ── Exchange fee table (taker fees) ──────────────────────────────────────────
TAKER_FEES: dict[str, float] = {
    "delta":   0.00050,   # 0.05%
    "binance": 0.00040,   # 0.04%
    "kite":    0.00030,   # 0.03% intraday
    "ib":      0.00100,   # 0.10% + min ticket
}

# ── Symbol → supported exchanges ─────────────────────────────────────────────
SYMBOL_EXCHANGE_MAP: dict[str, list[str]] = {
    # Crypto perpetuals
    "BTCUSD":   ["delta"],
    "ETHUSD":   ["delta"],
    "SOLUSD":   ["delta"],
    "BNBUSD":   ["delta"],
    "XRPUSD":   ["delta"],
    # Binance futures
    "BTCUSDT":  ["binance"],
    "ETHUSDT":  ["binance"],
    "SOLUSDT":  ["binance"],
    "BNBUSDT":  ["binance"],
    # NSE equity
    "RELIANCE": ["kite"],
    "TCS":      ["kite"],
    "NIFTY50":  ["kite"],
    "SENSEX":   ["kite"],
    # US equity
    "AAPL":     ["ib"],
    "MSFT":     ["ib"],
    "TSLA":     ["ib"],
}

# Crypto symbols available on both Delta + Binance
CROSS_LISTED = {
    "BTC": ["delta", "binance"],
    "ETH": ["delta", "binance"],
    "SOL": ["delta", "binance"],
}


@dataclass
class RoutingDecision:
    exchange:     str
    reason:       str
    fee_estimate: float
    alternatives: list[str]
    score:        float   = 0.0


class SmartRouter:
    """
    Routes each order to the most appropriate exchange.

    Priority rules:
        1. Manual override (request.exchange set to specific exchange)
        2. Paper mode → route to first exchange with valid paper token
        3. Token-gated → only routes to exchanges with ACTIVE tokens
        4. Liquidity → prefer exchange with tighter spread
        5. Fees → lower taker fee preferred
        6. Fallback → first available exchange for the symbol
    """

    def __init__(self, token_manager: TokenManager) -> None:
        self._tm = token_manager

    async def route(self, request: OrderRequest) -> RoutingDecision:
        """
        Determine best exchange for this order request.

        Returns a RoutingDecision with the chosen exchange and reason.
        Raises ValueError if no valid exchange can be found.
        """

        # ── 1. Manual override ───────────────────────────────────────────────
        if request.exchange and request.exchange != "auto":
            exch = request.exchange.lower()
            log.info("router.manual_override", exchange=exch, symbol=request.symbol)
            return RoutingDecision(
                exchange=exch,
                reason=f"Manual override — user specified {exch}",
                fee_estimate=TAKER_FEES.get(exch, 0.001) * request.quantity,
                alternatives=[],
            )

        candidates = self._get_candidates(request.symbol)
        if not candidates:
            raise ValueError(
                f"Symbol '{request.symbol}' not listed on any supported exchange. "
                "Check SYMBOL_EXCHANGE_MAP or specify exchange manually."
            )

        # ── 2. Filter by token validity ──────────────────────────────────────
        valid_candidates = self._filter_by_token(candidates)
        if not valid_candidates:
            log.warning("router.no_valid_tokens",
                        symbol=request.symbol, candidates=candidates)
            # Fall through to first candidate in paper mode
            valid_candidates = candidates

        # ── 3. Score each candidate ──────────────────────────────────────────
        scores = await self._score_exchanges(request, valid_candidates)
        best   = max(scores, key=lambda x: x["score"])

        decision = RoutingDecision(
            exchange=best["exchange"],
            reason=best["reason"],
            fee_estimate=TAKER_FEES.get(best["exchange"], 0.001) * request.quantity,
            alternatives=[s["exchange"] for s in scores if s["exchange"] != best["exchange"]],
            score=best["score"],
        )
        log.info("router.decision",
                 symbol=request.symbol, exchange=decision.exchange,
                 reason=decision.reason, score=round(decision.score, 3))
        return decision

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_candidates(self, symbol: str) -> list[str]:
        """Return exchanges that list this symbol."""
        direct = SYMBOL_EXCHANGE_MAP.get(symbol.upper(), [])
        if direct:
            return direct
        # Check cross-listed by base asset
        base = symbol[:3].upper()
        return CROSS_LISTED.get(base, [])

    def _filter_by_token(self, candidates: list[str]) -> list[str]:
        """Remove exchanges whose token is invalid/missing/expired."""
        valid = []
        for exch in candidates:
            try:
                ex_id = ExchangeID(exch)
                token = self._tm.get_token_safe(ex_id)
                if token is not None:
                    valid.append(exch)
            except (ValueError, Exception):
                pass
        return valid

    async def _score_exchanges(
        self, request: OrderRequest, candidates: list[str]
    ) -> list[dict]:
        """Score each exchange. Higher = better."""
        results = []
        for exch in candidates:
            score, reason = await self._score_one(request, exch)
            results.append({"exchange": exch, "score": score, "reason": reason})
        return sorted(results, key=lambda x: x["score"], reverse=True)

    async def _score_one(self, request: OrderRequest, exch: str) -> tuple[float, str]:
        score  = 1.0
        reason = f"Default selection for {exch}"

        # Fee penalty (lower fees = higher score)
        fee = TAKER_FEES.get(exch, 0.001)
        score -= fee * 100   # Scale fee impact

        # Liquidity bonus (try to fetch live spread)
        spread = await self._fetch_spread(exch, request.symbol)
        if spread is not None:
            score += max(0, 0.5 - spread * 100)   # Tighter spread → higher bonus
            reason = f"Best spread {spread:.4%} on {exch}"

        # Prefer native exchange for instrument
        native = SYMBOL_EXCHANGE_MAP.get(request.symbol.upper(), [])
        if exch in native and len(native) == 1:
            score += 0.5
            reason = f"Native listing on {exch}"

        # Paper mode bonus for consistency
        try:
            ex_id = ExchangeID(exch)
            token = self._tm.get_token_safe(ex_id)
            if token and token.paper_mode:
                score += 0.2
        except ValueError:
            pass

        return score, reason

    async def _fetch_spread(self, exchange: str, symbol: str) -> Optional[float]:
        """Fetch bid-ask spread. Returns None on failure."""
        try:
            if exchange == "delta":
                from alchemy.execution.crypto.delta_gateway import DeltaGateway
                gw  = DeltaGateway(paper_trading=True, testnet_mode=True)
                ob  = gw.get_orderbook(symbol, depth=1)
                bids = ob.get("buy", [])
                asks = ob.get("sell", [])
                if bids and asks:
                    spread = (float(asks[0]["price"]) - float(bids[0]["price"])) / float(asks[0]["price"])
                    return spread
            elif exchange == "binance":
                from alchemy.execution.crypto.binance_gateway import BinanceGateway
                gw  = BinanceGateway(paper_trading=True, testnet=True)
                ob  = gw.get_orderbook(symbol, limit=5)
                if ob.get("bids") and ob.get("asks"):
                    spread = (float(ob["asks"][0][0]) - float(ob["bids"][0][0])) / float(ob["asks"][0][0])
                    return spread
        except Exception:
            pass
        return None
