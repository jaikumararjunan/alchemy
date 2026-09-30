"""
alchemy.execution.dhan_gateway
===============================
DhanHQ v2 execution + market-data gateway (NSE / BSE / NFO / MCX).
Docs: https://dhanhq.co/docs/v2/

Talks to the REST API directly with httpx (no SDK dependency).

Safety model
------------
  * ``paper_trading=True`` is the default — no request that moves money is ever sent.
  * In live mode every order passes ``_guard_order``: quantity cap, order-value cap
    (market orders are valued at LTP; if LTP is unavailable the order is refused)
    and a local kill switch.
  * Dhan's own account-level kill switch is exposed via ``activate_kill_switch``.

Auth: Dhan issues a static access token (valid up to 30 days) from
web.dhan.co → My Profile → Access DhanHQ APIs. No TOTP flow is needed.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from typing import Any, Literal, Optional

import httpx
import structlog

from alchemy.core.state import TradingSignal

log = structlog.get_logger(__name__)

BASE_URL    = "https://api.dhan.co/v2"
SCRIP_MASTER = "https://images.dhan.co/api-data/api-scrip-master.csv"

ExchangeSegment = Literal[
    "NSE_EQ", "NSE_FNO", "NSE_CURRENCY", "BSE_EQ", "BSE_FNO", "BSE_CURRENCY", "MCX_COMM", "IDX_I",
]
TransactionType = Literal["BUY", "SELL"]
ProductType     = Literal["CNC", "INTRADAY", "MARGIN", "MTF", "CO", "BO"]
OrderType       = Literal["LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"]
Validity        = Literal["DAY", "IOC"]

# exchange + segment letters in the scrip master -> Dhan exchangeSegment
_SEGMENT_MAP = {
    ("NSE", "E"): "NSE_EQ",  ("BSE", "E"): "BSE_EQ",
    ("NSE", "D"): "NSE_FNO", ("BSE", "D"): "BSE_FNO",
    ("NSE", "C"): "NSE_CURRENCY", ("MCX", "M"): "MCX_COMM",
}


class DhanError(RuntimeError):
    """Raised for API errors and safety-guard refusals."""


class DhanGateway:
    """
    Usage::

        gw = DhanGateway(client_id="1000000123", access_token="...", paper_trading=True)
        gw.connect()
        sec = gw.find_instrument("RELIANCE")                # -> {"security_id": "2885", ...}
        gw.get_ltp({"NSE_EQ": [int(sec["security_id"])]})
        gw.place_order(security_id=sec["security_id"], exchange_segment="NSE_EQ",
                       transaction_type="BUY", quantity=1)
    """

    _scrip_cache: Optional[list[dict]] = None
    _scrip_lock = threading.Lock()

    def __init__(
        self,
        client_id: str,
        access_token: str,
        paper_trading: bool = True,
        max_order_value: float = 50_000.0,
        max_order_qty: int = 1_000,
        timeout: float = 10.0,
    ) -> None:
        self.client_id       = client_id
        self.access_token    = access_token
        self.paper           = paper_trading
        self.max_order_value = max_order_value
        self.max_order_qty   = max_order_qty
        self.kill_switch     = False          # local kill switch: blocks all new orders
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={
                "access-token": access_token,
                "client-id":    client_id,
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
        )
        self._paper_orders: list[dict] = []
        self._last_quote_call = 0.0
        log.info("dhan.init", paper=paper_trading, max_order_value=max_order_value)

    # ── Low-level ────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise DhanError(f"Dhan network error: {e}") from e
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:300]}
        if r.status_code >= 400:
            msg = (body.get("errorMessage") or body.get("remarks") or body) if isinstance(body, dict) else body
            raise DhanError(f"Dhan {r.status_code}: {msg}")
        return body

    def _throttle_quotes(self) -> None:
        """Market-feed endpoints allow ~1 request/second."""
        wait = 1.05 - (time.monotonic() - self._last_quote_call)
        if wait > 0:
            time.sleep(wait)
        self._last_quote_call = time.monotonic()

    # ── Connection ───────────────────────────────────────────────────────────

    def connect(self) -> dict:
        """Validate credentials. Uses the read-only /fundlimit call, so it is safe in any mode."""
        funds = self._request("GET", "/fundlimit")
        log.info("dhan.connected", client=self.client_id)
        return funds

    def close(self) -> None:
        self._http.close()

    # ── Instruments ──────────────────────────────────────────────────────────

    @classmethod
    def _load_scrips(cls) -> list[dict]:
        with cls._scrip_lock:
            if cls._scrip_cache is None:
                r = httpx.get(SCRIP_MASTER, timeout=60, follow_redirects=True)
                r.raise_for_status()
                cls._scrip_cache = list(csv.DictReader(io.StringIO(r.text)))
                log.info("dhan.scrip_master_loaded", rows=len(cls._scrip_cache))
            return cls._scrip_cache

    def find_instrument(
        self, symbol: str, exchange: str = "NSE", instrument: str = "EQUITY"
    ) -> Optional[dict]:
        """Resolve a trading symbol (e.g. RELIANCE) to Dhan's securityId via the scrip master."""
        sym = symbol.upper().replace("-EQ", "")
        for row in self._load_scrips():
            if (row.get("SEM_EXM_EXCH_ID") == exchange
                    and row.get("SEM_INSTRUMENT_NAME") == instrument
                    and row.get("SEM_TRADING_SYMBOL", "").upper() == sym):
                seg = _SEGMENT_MAP.get((exchange, row.get("SEM_SEGMENT", "")))
                return {
                    "symbol": sym,
                    "security_id": row["SEM_SMST_SECURITY_ID"],
                    "exchange_segment": seg,
                    "lot_size": row.get("SEM_LOT_UNITS"),
                    "name": row.get("SEM_CUSTOM_SYMBOL"),
                }
        return None

    # ── Market data (read-only) ──────────────────────────────────────────────

    def get_ltp(self, instruments: dict[str, list[int]]) -> dict:
        """instruments = {"NSE_EQ": [2885, 1333]} -> last traded prices."""
        self._throttle_quotes()
        return self._request("POST", "/marketfeed/ltp", json=instruments)

    def get_ohlc(self, instruments: dict[str, list[int]]) -> dict:
        self._throttle_quotes()
        return self._request("POST", "/marketfeed/ohlc", json=instruments)

    def get_quote(self, instruments: dict[str, list[int]]) -> dict:
        """Full quote incl. market depth, volume, OI."""
        self._throttle_quotes()
        return self._request("POST", "/marketfeed/quote", json=instruments)

    def get_historical(
        self, security_id: str, exchange_segment: str, instrument: str,
        from_date: str, to_date: str,
    ) -> dict:
        """Daily candles. Dates are YYYY-MM-DD."""
        return self._request("POST", "/charts/historical", json={
            "securityId": security_id, "exchangeSegment": exchange_segment,
            "instrument": instrument, "expiryCode": 0,
            "fromDate": from_date, "toDate": to_date,
        })

    def get_intraday(
        self, security_id: str, exchange_segment: str, instrument: str,
        from_date: str, to_date: str, interval: int = 5,
    ) -> dict:
        """Intraday candles. interval in minutes: 1, 5, 15, 25, 60. Dates 'YYYY-MM-DD HH:MM:SS'."""
        return self._request("POST", "/charts/intraday", json={
            "securityId": security_id, "exchangeSegment": exchange_segment,
            "instrument": instrument, "interval": str(interval),
            "fromDate": from_date, "toDate": to_date,
        })

    # ── Account (read-only) ──────────────────────────────────────────────────

    def get_funds(self) -> dict:
        return self._request("GET", "/fundlimit")

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/positions") or []

    def get_holdings(self) -> list[dict]:
        return self._request("GET", "/holdings") or []

    def get_order_book(self) -> list[dict]:
        if self.paper:
            return list(self._paper_orders)
        return self._request("GET", "/orders") or []

    def get_order(self, order_id: str) -> dict:
        if self.paper:
            return next((o for o in self._paper_orders if o["orderId"] == order_id), {})
        return self._request("GET", f"/orders/{order_id}")

    def get_trade_book(self) -> list[dict]:
        return self._request("GET", "/trades") or []

    # ── Trading ──────────────────────────────────────────────────────────────

    def _guard_order(
        self, security_id: str, exchange_segment: str, quantity: int,
        order_type: str, price: float,
    ) -> float:
        """Refuse anything outside configured limits. Returns estimated order value."""
        if self.kill_switch:
            raise DhanError("Kill switch is active — new orders are blocked.")
        if quantity <= 0:
            raise DhanError("quantity must be positive")
        if quantity > self.max_order_qty:
            raise DhanError(f"quantity {quantity} exceeds max_order_qty {self.max_order_qty}")

        ref_price = price
        if order_type in ("MARKET", "STOP_LOSS_MARKET") or ref_price <= 0:
            try:
                data = self.get_ltp({exchange_segment: [int(security_id)]})
                ref_price = float(data["data"][exchange_segment][str(security_id)]["last_price"])
            except Exception as e:
                raise DhanError(f"Cannot value order (LTP unavailable): {e}") from e
        value = ref_price * quantity
        if value > self.max_order_value:
            raise DhanError(
                f"Order value ₹{value:,.0f} exceeds max_order_value ₹{self.max_order_value:,.0f}"
            )
        return value

    def place_order(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        transaction_type: TransactionType,
        quantity: int,
        order_type: OrderType = "MARKET",
        product_type: ProductType = "INTRADAY",
        price: float = 0.0,
        trigger_price: float = 0.0,
        validity: Validity = "DAY",
        after_market: bool = False,
        correlation_id: Optional[str] = None,
    ) -> dict:
        """Place an order. In paper mode nothing is sent to Dhan."""
        if order_type in ("LIMIT", "STOP_LOSS") and price <= 0:
            raise DhanError(f"{order_type} order needs a price")
        if order_type in ("STOP_LOSS", "STOP_LOSS_MARKET") and trigger_price <= 0:
            raise DhanError(f"{order_type} order needs a trigger_price")

        if self.paper:
            order = {
                "orderId": f"DHAN_PAPER_{int(time.time() * 1000)}",
                "orderStatus": "TRADED", "securityId": str(security_id),
                "exchangeSegment": exchange_segment, "transactionType": transaction_type,
                "quantity": quantity, "orderType": order_type, "productType": product_type,
                "price": price, "mode": "paper",
            }
            self._paper_orders.append(order)
            log.info("dhan.paper_order", **{k: order[k] for k in ("orderId", "securityId", "transactionType", "quantity")})
            return order

        value = self._guard_order(security_id, exchange_segment, quantity, order_type, price)
        payload = {
            "dhanClientId":    self.client_id,
            "transactionType": transaction_type,
            "exchangeSegment": exchange_segment,
            "productType":     product_type,
            "orderType":       order_type,
            "validity":        validity,
            "securityId":      str(security_id),
            "quantity":        int(quantity),
            "price":           float(price),
            "afterMarketOrder": after_market,
        }
        if trigger_price:
            payload["triggerPrice"] = float(trigger_price)
        if correlation_id:
            payload["correlationId"] = correlation_id[:25]

        result = self._request("POST", "/orders", json=payload)
        log.warning("dhan.LIVE_order_placed", security_id=security_id, side=transaction_type,
                    qty=quantity, est_value=round(value, 2), order_id=result.get("orderId"))
        return result

    def modify_order(
        self, order_id: str, order_type: OrderType, quantity: int,
        price: float = 0.0, trigger_price: float = 0.0, validity: Validity = "DAY",
    ) -> dict:
        if self.paper:
            return {"orderId": order_id, "orderStatus": "MODIFIED", "mode": "paper"}
        payload = {
            "dhanClientId": self.client_id, "orderId": order_id, "orderType": order_type,
            "quantity": int(quantity), "price": float(price), "validity": validity,
        }
        if trigger_price:
            payload["triggerPrice"] = float(trigger_price)
        return self._request("PUT", f"/orders/{order_id}", json=payload)

    def cancel_order(self, order_id: str) -> dict:
        if self.paper:
            for o in self._paper_orders:
                if o["orderId"] == order_id:
                    o["orderStatus"] = "CANCELLED"
            return {"orderId": order_id, "orderStatus": "CANCELLED", "mode": "paper"}
        return self._request("DELETE", f"/orders/{order_id}")

    # ── Kill switch ──────────────────────────────────────────────────────────

    def activate_kill_switch(self) -> dict:
        """Blocks locally AND asks Dhan to disable trading for the account for the day.
        Dhan requires no open positions / pending orders for the account-level switch."""
        self.kill_switch = True
        if self.paper:
            return {"killSwitchStatus": "ACTIVATE", "mode": "paper"}
        return self._request("POST", "/killswitch", params={"killSwitchStatus": "ACTIVATE"})

    def deactivate_kill_switch(self) -> dict:
        self.kill_switch = False
        if self.paper:
            return {"killSwitchStatus": "DEACTIVATE", "mode": "paper"}
        return self._request("POST", "/killswitch", params={"killSwitchStatus": "DEACTIVATE"})

    # ── TradingSignal integration ────────────────────────────────────────────

    def execute_signal(self, signal: TradingSignal, portfolio_value: float) -> Optional[str]:
        """Execute an Alchemy TradingSignal as an INTRADAY NSE equity market order."""
        if signal.signal == "HOLD":
            return None
        inst = self.find_instrument(signal.ticker)
        if not inst:
            log.warning("dhan.unknown_symbol", ticker=signal.ticker)
            return None
        ltp = self.get_ltp({inst["exchange_segment"]: [int(inst["security_id"])]})
        price = float(ltp["data"][inst["exchange_segment"]][inst["security_id"]]["last_price"])
        qty = max(1, int(portfolio_value * signal.position_pct / price))
        res = self.place_order(
            security_id=inst["security_id"], exchange_segment=inst["exchange_segment"],
            transaction_type="BUY" if signal.signal == "BUY" else "SELL",
            quantity=qty, order_type="MARKET", product_type="INTRADAY",
            correlation_id=signal.run_id,
        )
        return res.get("orderId")

    def __enter__(self) -> "DhanGateway":
        return self

    def __exit__(self, *a: object) -> None:
        self.close()
