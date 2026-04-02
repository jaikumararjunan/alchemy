"""
alchemy.execution.ib_gateway
=============================
Interactive Brokers execution gateway using ib_insync.
Based on: https://github.com/QuantInsti/ib-controller
          https://github.com/QuantInsti/QuantInsti-Live-Algo-Trading-Setups

Connects to IB Gateway / TWS (managed by ib-controller) via localhost.
Wraps order placement, portfolio retrieval, and live market data.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import structlog

from alchemy.core.config import IBConfig, get_config
from alchemy.core.state import TradingSignal

log = structlog.get_logger(__name__)


class IBGateway:
    """
    Interactive Brokers execution gateway.

    Prerequisites:
        1. IB Gateway or TWS running (managed by ib-controller Java process)
        2. API connections enabled in TWS/Gateway settings
        3. Paper or live account configured

    Usage::

        gw = IBGateway()
        gw.connect()
        order_id = gw.execute_signal(signal, portfolio_value=100_000)
        portfolio = gw.get_portfolio()
        gw.disconnect()
    """

    def __init__(self, config: Optional[IBConfig] = None) -> None:
        self.cfg = config or get_config().ib
        self._ib = None
        self._connected = False

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to IB Gateway. Returns True if successful."""
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(
                self.cfg.host,
                self.cfg.port,
                clientId=self.cfg.client_id,
                readonly=False,
                timeout=10,
            )
            self._connected = self._ib.isConnected()
            if self._connected:
                log.info("ib.connected",
                         host=self.cfg.host, port=self.cfg.port,
                         account=self.cfg.account or "default",
                         paper=self.cfg.paper_trading)
            return self._connected
        except ImportError:
            log.error("ib.insync_not_installed",
                      hint="pip install ib_insync")
            return False
        except Exception as e:
            log.error("ib.connect_failed", error=str(e))
            return False

    def disconnect(self) -> None:
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False
            log.info("ib.disconnected")

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute_signal(
        self, signal: TradingSignal, portfolio_value: float
    ) -> Optional[str]:
        """
        Convert a TradingSignal into an IB order and submit it.

        Returns:
            Order ID string if successful, None otherwise.
        """
        self._require_connection()

        if signal.signal == "HOLD":
            log.info("ib.skip_hold", ticker=signal.ticker)
            return None

        qty = self._compute_quantity(signal, portfolio_value)
        if qty == 0:
            log.warning("ib.zero_quantity", ticker=signal.ticker)
            return None

        try:
            from ib_insync import Stock, MarketOrder, LimitOrder
            contract = Stock(signal.ticker, "SMART", "USD")
            action   = "BUY" if signal.signal == "BUY" else "SELL"
            order    = MarketOrder(action, qty)

            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)  # Allow fill acknowledgement

            order_id = str(trade.order.orderId)
            log.info("ib.order_placed",
                     ticker=signal.ticker, action=action,
                     qty=qty, order_id=order_id,
                     status=trade.orderStatus.status)
            return order_id

        except Exception as e:
            log.error("ib.order_failed", ticker=signal.ticker, error=str(e))
            return None

    def cancel_all_orders(self) -> int:
        """Emergency: cancel all open orders. Returns count cancelled."""
        self._require_connection()
        open_orders = self._ib.openOrders()
        for order in open_orders:
            self._ib.cancelOrder(order)
        log.warning("ib.all_orders_cancelled", count=len(open_orders))
        return len(open_orders)

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_portfolio(self) -> list[dict]:
        """Return current positions as list of dicts."""
        self._require_connection()
        positions = []
        for pos in self._ib.portfolio():
            positions.append({
                "symbol":       pos.contract.symbol,
                "position":     pos.position,
                "market_price": pos.marketPrice,
                "market_value": pos.marketValue,
                "avg_cost":     pos.averageCost,
                "unrealised_pnl": pos.unrealizedPNL,
                "realised_pnl":   pos.realizedPNL,
            })
        return positions

    def get_account_value(self) -> float:
        """Return total net liquidation value."""
        self._require_connection()
        summary = self._ib.accountSummary()
        for item in summary:
            if item.tag == "NetLiquidation" and item.currency == "USD":
                return float(item.value)
        return 0.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_quantity(self, signal: TradingSignal, portfolio_value: float) -> int:
        """Convert target position % to share quantity."""
        target_value = portfolio_value * signal.position_pct
        # Use a rough price estimate (real impl: fetch live price from IB)
        price = signal.forecast_vol * 1000  # placeholder
        if price <= 0:
            return 0
        return max(0, int(target_value / price))

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError(
                "Not connected to IB Gateway. Call .connect() first."
            )

    def __enter__(self) -> "IBGateway":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.disconnect()
