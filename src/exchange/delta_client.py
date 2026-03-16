"""
Delta Exchange API client.
Supports REST API for order management, account info, and market data.
"""

import hashlib
import hmac
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Order:
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str  # "limit" or "market"
    size: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    reduce_only: bool = False
    time_in_force: str = "gtc"


@dataclass
class Position:
    symbol: str
    size: float
    side: str
    entry_price: float
    liquidation_price: float
    unrealized_pnl: float
    realized_pnl: float
    leverage: int


@dataclass
class Ticker:
    symbol: str
    mark_price: float
    last_price: float
    bid: float
    ask: float
    volume_24h: float
    change_24h_pct: float
    open_interest: float


class DeltaExchangeClient:
    """
    Client for the Delta Exchange API.
    Handles authentication, REST requests, and core trading operations.
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "Alchemy-Trader/1.0",
            }
        )

    def _sign(self, method: str, path: str, timestamp: str, body: str = "") -> str:
        message = method + timestamp + path + body
        return hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time()))
        signature = self._sign(method.upper(), path, timestamp, body)
        return {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body_str = ""

        if json_body:
            import json

            body_str = json.dumps(json_body, separators=(",", ":"))

        headers = {}
        if auth:
            headers = self._get_headers(method, path, body_str)

        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                data=body_str if body_str else None,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout: {method} {path}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP error {e.response.status_code}: {method} {path} - {e.response.text}"
            )
            raise
        except Exception as e:
            logger.error(f"Request error: {method} {path} - {e}")
            raise

    # -------------------------
    # Market Data (no auth)
    # -------------------------

    def get_products(self) -> List[Dict]:
        """Get all available trading products."""
        resp = self._request("GET", "/v2/products", auth=False)
        return resp.get("result", [])

    def get_ticker(self, symbol: str) -> Ticker:
        """Get current ticker for a symbol."""
        resp = self._request("GET", f"/v2/tickers/{symbol}", auth=False)
        data = resp.get("result", {})
        # Delta Exchange ticker uses turnover_24h for USD volume (volume = contract count)
        # bid/ask are not in the ticker response; callers needing them should use get_orderbook()
        return Ticker(
            symbol=symbol,
            mark_price=float(data.get("mark_price", 0)),
            last_price=float(data.get("close", 0)),
            bid=float(data.get("best_bid_price", data.get("bid", 0))),
            ask=float(data.get("best_ask_price", data.get("ask", 0))),
            volume_24h=float(data.get("turnover_24h", data.get("volume", 0))),
            change_24h_pct=float(data.get("price_change_24h_pcnt", 0)),
            open_interest=float(data.get("open_interest", 0)),
        )

    def get_orderbook(self, symbol: str, depth: int = 10) -> Dict:
        """Get order book for a symbol."""
        resp = self._request(
            "GET", f"/v2/l2orderbook/{symbol}", params={"depth": depth}, auth=False
        )
        return resp.get("result", {})

    def get_candles(
        self,
        symbol: str,
        resolution: int = 60,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get OHLCV candle data.
        resolution: candle size in seconds (60=1m, 300=5m, 3600=1h, 86400=1d)
        """
        params: Dict[str, Any] = {"resolution": resolution}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        resp = self._request(
            "GET",
            "/v2/history/candles",
            params={"symbol": symbol, **params},
            auth=False,
        )
        return resp.get("result", [])

    # -------------------------
    # Account (auth required)
    # -------------------------

    def get_wallet_balance(self, asset: str = "USDT") -> Dict:
        """Get wallet balance for an asset."""
        resp = self._request("GET", "/v2/wallet/balances", auth=True)
        balances = resp.get("result", [])
        for bal in balances:
            if bal.get("asset_symbol") == asset:
                return {
                    "asset": asset,
                    "balance": float(bal.get("balance", 0)),
                    "available_balance": float(bal.get("available_balance", 0)),
                    "blocked_margin": float(bal.get("blocked_margin", 0)),
                }
        return {
            "asset": asset,
            "balance": 0.0,
            "available_balance": 0.0,
            "blocked_margin": 0.0,
        }

    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        resp = self._request("GET", "/v2/positions/margined", auth=True)
        positions = []
        for p in resp.get("result", []):
            size = float(p.get("size", 0))
            if size == 0:
                continue
            positions.append(
                Position(
                    symbol=p.get("product_symbol", ""),
                    size=abs(size),
                    side="long" if size > 0 else "short",
                    entry_price=float(p.get("entry_price", 0)),
                    liquidation_price=float(p.get("liquidation_price", 0)),
                    unrealized_pnl=float(p.get("unrealized_pnl", 0)),
                    realized_pnl=float(p.get("realized_pnl", 0)),
                    leverage=int(p.get("leverage", {}).get("value", 1)),
                )
            )
        return positions

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["product_symbol"] = symbol
        resp = self._request("GET", "/v2/orders", params=params, auth=True)
        return resp.get("result", [])

    # -------------------------
    # Order Management (auth)
    # -------------------------

    def place_order(self, order: Order, product_id: int) -> Dict:
        """Place a new order."""
        body: Dict[str, Any] = {
            "product_id": product_id,
            "side": order.side,
            "order_type": order.order_type,
            "size": str(int(order.size)),
            "time_in_force": order.time_in_force,
            "reduce_only": order.reduce_only,
        }
        if order.price and order.order_type == "limit":
            body["limit_price"] = str(order.price)
        if order.stop_price:
            body["stop_price"] = str(order.stop_price)

        resp = self._request("POST", "/v2/orders", json_body=body, auth=True)
        logger.info(
            f"Order placed: {order.side} {order.size} {order.symbol} @ {order.price or 'market'}"
        )
        return resp.get("result", {})

    def cancel_order(self, order_id: int, product_id: int) -> Dict:
        """Cancel an existing order."""
        body = {"id": order_id, "product_id": product_id}
        resp = self._request("DELETE", "/v2/orders", json_body=body, auth=True)
        return resp.get("result", {})

    def cancel_all_orders(self, product_id: int, side: Optional[str] = None) -> Dict:
        """Cancel all open orders for a product."""
        body: Dict[str, Any] = {"product_id": product_id}
        if side:
            body["side"] = side
        resp = self._request("DELETE", "/v2/orders/all", json_body=body, auth=True)
        return resp.get("result", {})

    def set_leverage(self, product_id: int, leverage: int) -> Dict:
        """Set leverage for a product."""
        body = {"product_id": product_id, "leverage": leverage}
        resp = self._request(
            "POST", "/v2/products/orders/leverage", json_body=body, auth=True
        )
        return resp.get("result", {})

    def close_position(self, product_id: int, symbol: str) -> Dict:
        """Close an open position using a market order."""
        positions = self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                close_side = "sell" if pos.side == "long" else "buy"
                order = Order(
                    symbol=symbol,
                    side=close_side,
                    order_type="market",
                    size=pos.size,
                    reduce_only=True,
                )
                return self.place_order(order, product_id)
        logger.warning(f"No open position found for {symbol}")
        return {}

    def get_product_id(self, symbol: str) -> Optional[int]:
        """Look up the product ID for a given symbol."""
        products = self.get_products()
        for p in products:
            if p.get("symbol") == symbol:
                return p.get("id")
        return None
