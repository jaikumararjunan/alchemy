"""
alchemy.execution.crypto.delta_gateway
=======================================
Delta Exchange crypto derivatives gateway.
Delta Exchange: https://www.delta.exchange

Supports perpetual futures, options, move contracts and spreads
for BTC, ETH, SOL and other crypto assets.

API Docs: https://docs.delta.exchange/
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Literal, Optional
from urllib.parse import urlencode

import httpx
import structlog

from alchemy.core.config import get_config

log = structlog.get_logger(__name__)

OrderSide   = Literal["buy", "sell"]
OrderType   = Literal["market_order", "limit_order", "stop_market_order"]
TimeInForce = Literal["gtc", "ioc", "fok"]
ProductType = Literal["perpetual_futures", "call_options", "put_options", "move", "spot"]


class DeltaGateway:
    """
    Delta Exchange REST + WebSocket gateway.

    Features:
        - Perpetual futures trading (BTC, ETH, SOL, BNB, XRP, …)
        - Options trading (calls + puts)
        - MOVE contracts (volatility products)
        - Real-time order book and ticker data
        - Position management with leverage control
        - Funding rate retrieval
        - Paper trading via simulated mode

    Setup:
        1. Create API key at https://www.delta.exchange/app/account/manageapikey
        2. Set DELTA_API_KEY and DELTA_API_SECRET in environment
        3. Use testnet_mode=True for development

    Usage::

        gw = DeltaGateway(testnet_mode=True)
        ticker = gw.get_ticker("BTCUSD")
        order  = gw.place_order("BTCUSD", side="buy", size=1,
                                 order_type="market_order", leverage=10)
    """

    MAINNET_URL = "https://api.delta.exchange"
    TESTNET_URL = "https://testnet-api.delta.exchange"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet_mode: bool = True,
        paper_trading: bool = True,
    ) -> None:
        cfg = get_config()
        self.api_key    = api_key    or getattr(cfg, "delta_api_key",    None)
        self.api_secret = api_secret or getattr(cfg, "delta_api_secret", None)
        self.testnet    = testnet_mode
        self.paper      = paper_trading
        self.base_url   = self.TESTNET_URL if testnet_mode else self.MAINNET_URL
        self._client    = httpx.Client(base_url=self.base_url, timeout=15.0)
        log.info("delta.init", testnet=testnet_mode, paper=paper_trading)

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_products(self, product_type: Optional[ProductType] = None) -> list[dict]:
        """List all available products (contracts)."""
        params = {}
        if product_type:
            params["contract_types"] = product_type
        return self._get("/v2/products", params)

    def get_ticker(self, symbol: str) -> dict:
        """
        Get real-time ticker for a product.

        Returns:
            dict with mark_price, spot_price, funding_rate, open_interest,
            volume, 24h change, best_bid, best_ask.
        """
        r = self._get(f"/v2/tickers/{symbol}")
        log.debug("delta.ticker", symbol=symbol, mark=r.get("mark_price"))
        return r

    def get_orderbook(self, symbol: str, depth: int = 10) -> dict:
        """Get order book snapshot."""
        return self._get(f"/v2/l2orderbook/{symbol}", {"depth": depth})

    def get_klines(
        self, symbol: str, resolution: str = "1h",
        start: Optional[int] = None, end: Optional[int] = None
    ) -> list[dict]:
        """
        OHLCV candlestick data.

        Args:
            symbol:     e.g. "BTCUSD"
            resolution: 1m | 5m | 15m | 30m | 1h | 2h | 4h | 6h | 1d | 1w
        """
        params: dict[str, Any] = {"symbol": symbol, "resolution": resolution}
        if start: params["start"] = start
        if end:   params["end"]   = end
        return self._get("/v2/history/candles", params)

    def get_funding_rate(self, symbol: str) -> dict:
        """Get current and predicted funding rate for a perpetual."""
        return self._get(f"/v2/products/{symbol}/funding_rate")

    # ── Account ───────────────────────────────────────────────────────────────

    def get_wallet_balance(self) -> list[dict]:
        """Get wallet balances for all assets."""
        return self._get_auth("/v2/wallet/balances")

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        return self._get_auth("/v2/positions/margined")

    def get_orders(self, state: str = "open") -> list[dict]:
        """Get orders by state: open | closed | cancelled | all."""
        return self._get_auth("/v2/orders", {"state": state})

    def get_order_history(self, symbol: Optional[str] = None) -> list[dict]:
        params = {}
        if symbol: params["product_symbol"] = symbol
        return self._get_auth("/v2/orders/history", params)

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        size: int,
        order_type: OrderType = "market_order",
        limit_price: Optional[float] = None,
        stop_price:  Optional[float] = None,
        leverage:    int = 1,
        reduce_only: bool = False,
        time_in_force: TimeInForce = "gtc",
        post_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> dict:
        """
        Place a new order on Delta Exchange.

        Args:
            symbol:    Product symbol, e.g. "BTCUSD" (perpetual) or "BTC-31MAY24-60000-C" (option)
            side:      "buy" (long) | "sell" (short)
            size:      Number of contracts (integer)
            leverage:  Leverage multiplier (1–100 for perps)

        Returns:
            Order confirmation dict with id, state, avg_fill_price.
        """
        if self.paper:
            return self._paper_order(symbol, side, size, order_type, leverage)

        product = self._resolve_product_id(symbol)
        payload: dict[str, Any] = {
            "product_id":    product,
            "side":          side,
            "size":          size,
            "order_type":    order_type,
            "time_in_force": time_in_force,
            "reduce_only":   reduce_only,
        }
        if limit_price:       payload["limit_price"]       = str(limit_price)
        if stop_price:        payload["stop_price"]        = str(stop_price)
        if post_only:         payload["post_only"]         = True
        if client_order_id:   payload["client_order_id"]   = client_order_id
        if leverage > 1:
            self.set_leverage(symbol, leverage)

        result = self._post_auth("/v2/orders", payload)
        log.info("delta.order_placed",
                 symbol=symbol, side=side, size=size,
                 order_id=result.get("id"), state=result.get("state"))
        return result

    def cancel_order(self, order_id: int, product_id: int) -> dict:
        return self._delete_auth("/v2/orders", {"id": order_id, "product_id": product_id})

    def cancel_all_orders(self, symbol: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {"cancel_limit_orders": True, "cancel_stop_orders": True}
        if symbol:
            payload["product_id"] = self._resolve_product_id(symbol)
        return self._delete_auth("/v2/orders/all", payload)

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """Set leverage for a product."""
        return self._post_auth("/v2/products/leverage", {
            "product_id": self._resolve_product_id(symbol),
            "leverage":   leverage,
        })

    def close_position(self, symbol: str) -> dict:
        """Close an entire open position at market price."""
        positions = self.get_positions()
        for pos in positions:
            if pos.get("product_symbol") == symbol and pos.get("size", 0) != 0:
                close_side = "sell" if pos["size"] > 0 else "buy"
                return self.place_order(
                    symbol, side=close_side,
                    size=abs(pos["size"]),
                    order_type="market_order",
                    reduce_only=True,
                )
        return {"message": f"No open position for {symbol}"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_product_id(self, symbol: str) -> int:
        """Resolve symbol string to numeric product ID."""
        products = self.get_products()
        for p in products:
            if p.get("symbol") == symbol:
                return p["id"]
        raise ValueError(f"Product not found: {symbol}")

    def _paper_order(self, symbol, side, size, order_type, leverage) -> dict:
        fake_id = int(time.time() * 1000)
        ticker  = self.get_ticker(symbol) if not self.testnet else {}
        price   = ticker.get("mark_price", 0)
        result  = {
            "id": fake_id, "symbol": symbol, "side": side,
            "size": size, "order_type": order_type, "leverage": leverage,
            "avg_fill_price": price, "state": "filled", "mode": "paper",
        }
        log.info("delta.paper_order", **{k: v for k, v in result.items() if k != "mode"})
        return result

    def _sign(self, method: str, path: str, body: str = "") -> dict[str, str]:
        ts      = str(int(time.time()))
        message = method + ts + path + body
        sig     = hmac.new(
            (self.api_secret or "").encode(),
            message.encode(), hashlib.sha256
        ).hexdigest()
        return {
            "api-key":   self.api_key or "",
            "timestamp": ts,
            "signature": sig,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = self._client.get(path, params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("result", data)

    def _get_auth(self, path: str, params: dict | None = None) -> Any:
        qs      = "?" + urlencode(params) if params else ""
        headers = self._sign("GET", path + qs)
        r       = self._client.get(path, params=params, headers=headers)
        r.raise_for_status()
        return r.json().get("result", r.json())

    def _post_auth(self, path: str, payload: dict) -> Any:
        import json
        body    = json.dumps(payload)
        headers = self._sign("POST", path, body)
        r       = self._client.post(path, content=body, headers=headers)
        r.raise_for_status()
        return r.json().get("result", r.json())

    def _delete_auth(self, path: str, payload: dict) -> Any:
        import json
        body    = json.dumps(payload)
        headers = self._sign("DELETE", path, body)
        r       = self._client.request("DELETE", path, content=body, headers=headers)
        r.raise_for_status()
        return r.json().get("result", r.json())

    def __enter__(self) -> "DeltaGateway":
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()
