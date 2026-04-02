"""
alchemy.execution.crypto.binance_gateway
=========================================
Binance spot and USD-M futures gateway.

Supports:
    - Spot trading (buy/sell crypto pairs)
    - USD-M Perpetual futures (BTCUSDT, ETHUSDT, …)
    - COIN-M futures (BTCUSD_PERP, …)
    - Funding rate retrieval
    - Position and balance management

API Docs: https://binance-docs.github.io/apidocs/
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

MarketType  = Literal["spot", "futures_usdm", "futures_coinm"]
OrderSide   = Literal["BUY", "SELL"]
OrderType   = Literal["MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"]
PositionSide = Literal["LONG", "SHORT", "BOTH"]


class BinanceGateway:
    """
    Binance exchange gateway — Spot and Futures.

    Supports both live and paper trading modes.
    Automatically handles HMAC-SHA256 request signing.

    Usage::

        gw = BinanceGateway(market="futures_usdm", paper_trading=True)

        ticker = gw.get_ticker("BTCUSDT")
        klines = gw.get_klines("ETHUSDT", interval="1h", limit=100)
        order  = gw.place_order("BTCUSDT", side="BUY", quantity=0.001,
                                 order_type="MARKET", leverage=10)
        pos    = gw.get_positions()
    """

    SPOT_URL         = "https://api.binance.com"
    FUTURES_USDM_URL = "https://fapi.binance.com"
    FUTURES_COINM_URL = "https://dapi.binance.com"
    TESTNET_FUTURES  = "https://testnet.binancefuture.com"

    def __init__(
        self,
        api_key:      Optional[str] = None,
        api_secret:   Optional[str] = None,
        market:       MarketType    = "futures_usdm",
        paper_trading: bool         = True,
        testnet:       bool         = False,
    ) -> None:
        cfg = get_config()
        self.api_key    = api_key    or getattr(cfg, "binance_api_key",    None)
        self.api_secret = api_secret or getattr(cfg, "binance_api_secret", None)
        self.market     = market
        self.paper      = paper_trading
        self.testnet    = testnet

        url_map = {
            "spot":          self.SPOT_URL,
            "futures_usdm":  self.TESTNET_FUTURES if testnet else self.FUTURES_USDM_URL,
            "futures_coinm": self.FUTURES_COINM_URL,
        }
        self.base_url = url_map[market]
        self._client  = httpx.Client(base_url=self.base_url, timeout=15.0)
        log.info("binance.init", market=market, paper=paper_trading, testnet=testnet)

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_ticker(self, symbol: str) -> dict:
        """24-hour rolling window ticker statistics."""
        endpoint = "/api/v3/ticker/24hr" if self.market == "spot" else "/fapi/v1/ticker/24hr"
        return self._get(endpoint, {"symbol": symbol})

    def get_price(self, symbol: str) -> float:
        """Latest mark/last price."""
        if self.market == "spot":
            r = self._get("/api/v3/ticker/price", {"symbol": symbol})
        else:
            r = self._get("/fapi/v1/ticker/price", {"symbol": symbol})
        return float(r.get("price", 0))

    def get_klines(
        self,
        symbol:   str,
        interval: str = "1h",
        limit:    int = 100,
        start_time: Optional[int] = None,
        end_time:   Optional[int] = None,
    ) -> list[list]:
        """
        OHLCV klines (candlesticks).

        Args:
            interval: 1m | 3m | 5m | 15m | 30m | 1h | 2h | 4h | 6h | 8h | 12h | 1d | 3d | 1w | 1M

        Returns:
            List of [open_time, open, high, low, close, volume, …]
        """
        endpoint = "/api/v3/klines" if self.market == "spot" else "/fapi/v1/klines"
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time: params["startTime"] = start_time
        if end_time:   params["endTime"]   = end_time
        return self._get(endpoint, params)

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """Order book depth snapshot."""
        endpoint = "/api/v3/depth" if self.market == "spot" else "/fapi/v1/depth"
        return self._get(endpoint, {"symbol": symbol, "limit": limit})

    def get_funding_rate(self, symbol: str, limit: int = 10) -> list[dict]:
        """Historical funding rates for a perpetual futures symbol."""
        return self._get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit})

    def get_mark_price(self, symbol: Optional[str] = None) -> dict | list:
        """Mark price and funding rate for perpetual."""
        params = {}
        if symbol: params["symbol"] = symbol
        return self._get("/fapi/v1/premiumIndex", params)

    def get_exchange_info(self) -> dict:
        """Exchange trading rules and symbol information."""
        endpoint = "/api/v3/exchangeInfo" if self.market == "spot" else "/fapi/v1/exchangeInfo"
        return self._get(endpoint)

    # ── Account ───────────────────────────────────────────────────────────────

    def get_balance(self) -> list[dict]:
        """Wallet balances for all assets."""
        if self.market == "spot":
            r = self._get_signed("/api/v3/account")
            return r.get("balances", [])
        return self._get_signed("/fapi/v2/balance")

    def get_positions(self) -> list[dict]:
        """All open futures positions (non-zero size)."""
        if self.market == "spot":
            return []
        all_pos = self._get_signed("/fapi/v2/positionRisk")
        return [p for p in all_pos if float(p.get("positionAmt", 0)) != 0]

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        endpoint = "/api/v3/openOrders" if self.market == "spot" else "/fapi/v1/openOrders"
        params: dict[str, Any] = {}
        if symbol: params["symbol"] = symbol
        return self._get_signed(endpoint, params)

    def get_income_history(self, income_type: str = "FUNDING_FEE") -> list[dict]:
        """Futures income history — useful for tracking funding fee P&L."""
        return self._get_signed("/fapi/v1/income", {"incomeType": income_type, "limit": 100})

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol:        str,
        side:          OrderSide,
        quantity:      float,
        order_type:    OrderType      = "MARKET",
        price:         Optional[float] = None,
        stop_price:    Optional[float] = None,
        leverage:      int             = 1,
        position_side: PositionSide   = "BOTH",
        reduce_only:   bool            = False,
        time_in_force: str             = "GTC",
    ) -> dict:
        """
        Place an order on Binance Spot or Futures.

        Args:
            symbol:   e.g. "BTCUSDT"
            side:     "BUY" | "SELL"
            quantity: Amount in base asset (e.g. 0.001 BTC)
            leverage: Set before placing futures order (1–125)

        Returns:
            Order confirmation dict.
        """
        if self.paper:
            return self._paper_order(symbol, side, quantity, order_type, leverage)

        if self.market != "spot" and leverage > 1:
            self.set_leverage(symbol, leverage)

        endpoint  = "/api/v3/order" if self.market == "spot" else "/fapi/v1/order"
        params: dict[str, Any] = {
            "symbol":   symbol,
            "side":     side,
            "type":     order_type,
            "quantity": self._format_qty(quantity),
        }
        if self.market != "spot":
            params["positionSide"] = position_side
            params["reduceOnly"]   = str(reduce_only).lower()

        if order_type == "LIMIT":
            params["price"]       = str(price)
            params["timeInForce"] = time_in_force
        elif order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            params["stopPrice"] = str(stop_price)

        result = self._post_signed(endpoint, params)
        log.info("binance.order_placed",
                 symbol=symbol, side=side, qty=quantity,
                 order_id=result.get("orderId"), status=result.get("status"))
        return result

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        endpoint = "/api/v3/order" if self.market == "spot" else "/fapi/v1/order"
        return self._delete_signed(endpoint, {"symbol": symbol, "orderId": order_id})

    def cancel_all_orders(self, symbol: str) -> dict:
        endpoint = "/api/v3/openOrders" if self.market == "spot" else "/fapi/v1/allOpenOrders"
        return self._delete_signed(endpoint, {"symbol": symbol})

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return self._post_signed("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> dict:
        """CROSSED | ISOLATED"""
        return self._post_signed("/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type})

    def close_position(self, symbol: str) -> dict:
        """Close an entire open position at market."""
        positions = self.get_positions()
        for pos in positions:
            if pos.get("symbol") == symbol:
                amt  = float(pos.get("positionAmt", 0))
                if amt == 0:
                    continue
                side = "SELL" if amt > 0 else "BUY"
                return self.place_order(
                    symbol, side=side, quantity=abs(amt),
                    order_type="MARKET", reduce_only=True,
                )
        return {"message": f"No open position for {symbol}"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _paper_order(self, symbol, side, quantity, order_type, leverage) -> dict:
        try:
            price = self.get_price(symbol)
        except Exception:
            price = 0.0
        result = {
            "orderId":      int(time.time() * 1000),
            "symbol":       symbol,
            "side":         side,
            "type":         order_type,
            "quantity":     str(quantity),
            "price":        str(price),
            "leverage":     leverage,
            "status":       "FILLED",
            "mode":         "paper",
            "executedQty":  str(quantity),
            "avgPrice":     str(price),
        }
        log.info("binance.paper_order", symbol=symbol, side=side, qty=quantity, price=price)
        return result

    def _format_qty(self, qty: float) -> str:
        return f"{qty:.8f}".rstrip("0").rstrip(".")

    def _sign_params(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        qs  = urlencode(params)
        sig = hmac.new(
            (self.api_secret or "").encode(),
            qs.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = sig
        return params

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key or ""}

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def _get_signed(self, path: str, params: dict | None = None) -> Any:
        p = self._sign_params(params or {})
        r = self._client.get(path, params=p, headers=self._auth_headers)
        r.raise_for_status()
        return r.json()

    def _post_signed(self, path: str, params: dict) -> Any:
        p = self._sign_params(params)
        r = self._client.post(path, params=p, headers=self._auth_headers)
        r.raise_for_status()
        return r.json()

    def _delete_signed(self, path: str, params: dict) -> Any:
        p = self._sign_params(params)
        r = self._client.delete(path, params=p, headers=self._auth_headers)
        r.raise_for_status()
        return r.json()

    def __enter__(self) -> "BinanceGateway":
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()
