"""
alchemy.execution.kite_gateway
================================
Zerodha Kite Connect execution gateway for Indian markets (NSE/BSE).
Based on: https://github.com/QuantInsti/kiteconnect3 (R patterns → Python)

Handles NSE equity, F&O, and currency execution via Kite Connect API v3.
"""
from __future__ import annotations

from typing import Optional

import structlog

from alchemy.core.config import KiteConfig, get_config
from alchemy.core.state import TradingSignal

log = structlog.get_logger(__name__)


class KiteGateway:
    """
    Zerodha Kite Connect execution gateway for Indian markets.

    Setup:
        1. Get API key from https://developers.kite.trade
        2. Generate access token (daily refresh via login flow)
        3. Set KITE_API_KEY and KITE_ACCESS_TOKEN in environment

    Usage::

        gw = KiteGateway()
        gw.connect()
        order_id = gw.execute_signal(signal, portfolio_value=1_000_000)
        positions = gw.get_positions()
    """

    EXCHANGE_MAP = {"NSE": "NSE", "BSE": "BSE"}
    PRODUCT_MIS  = "MIS"   # Intraday
    PRODUCT_CNC  = "CNC"   # Delivery / positional
    PRODUCT_NRML = "NRML"  # F&O / currency

    def __init__(self, config: Optional[KiteConfig] = None) -> None:
        self.cfg = config or get_config().kite
        self._kite = None

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Initialise KiteConnect with stored access token."""
        try:
            from kiteconnect import KiteConnect

            api_key = (self.cfg.api_key.get_secret_value()
                       if self.cfg.api_key else None)
            access_token = (self.cfg.access_token.get_secret_value()
                            if self.cfg.access_token else None)

            if not api_key:
                log.error("kite.no_api_key")
                return False

            self._kite = KiteConnect(api_key=api_key)
            if access_token:
                self._kite.set_access_token(access_token)

            # Validate by fetching profile
            profile = self._kite.profile()
            log.info("kite.connected",
                     user=profile.get("user_name"),
                     email=profile.get("email"),
                     paper=self.cfg.paper_trading)
            return True

        except ImportError:
            log.error("kite.not_installed", hint="pip install kiteconnect")
            return False
        except Exception as e:
            log.error("kite.connect_failed", error=str(e))
            return False

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute_signal(
        self,
        signal: TradingSignal,
        portfolio_value: float,
        product: str = PRODUCT_CNC,
    ) -> Optional[str]:
        """
        Place an order on NSE/BSE via Kite Connect.

        Args:
            signal:          TradingSignal from Alchemy agent.
            portfolio_value: Total portfolio NAV in INR.
            product:         CNC (delivery) | MIS (intraday) | NRML (F&O).

        Returns:
            Kite order_id string or None on failure.
        """
        if self.cfg.paper_trading:
            return self._paper_execute(signal, portfolio_value)

        self._require_connection()
        if signal.signal == "HOLD":
            return None

        qty = self._compute_quantity(signal, portfolio_value)
        if qty == 0:
            return None

        exchange = self.EXCHANGE_MAP.get(signal.market, "NSE")
        txn_type = (self._kite.TRANSACTION_TYPE_BUY
                    if signal.signal == "BUY"
                    else self._kite.TRANSACTION_TYPE_SELL)

        try:
            order_id = self._kite.place_order(
                tradingsymbol=signal.ticker,
                exchange=exchange,
                transaction_type=txn_type,
                quantity=qty,
                order_type=self._kite.ORDER_TYPE_MARKET,
                product=product,
                variety=self._kite.VARIETY_REGULAR,
            )
            log.info("kite.order_placed",
                     ticker=signal.ticker, exchange=exchange,
                     action=signal.signal, qty=qty, order_id=order_id)
            return str(order_id)

        except Exception as e:
            log.error("kite.order_failed", ticker=signal.ticker, error=str(e))
            return None

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_positions(self) -> dict:
        """Return open positions dict from Kite."""
        self._require_connection()
        return self._kite.positions()

    def get_holdings(self) -> list[dict]:
        """Return long-term holdings (CNC delivery)."""
        self._require_connection()
        return self._kite.holdings()

    def get_ltp(self, instruments: list[str], exchange: str = "NSE") -> dict:
        """
        Fetch last traded price for instruments.

        Args:
            instruments: e.g. ["RELIANCE", "TCS"]
            exchange:    "NSE" or "BSE"

        Returns:
            Dict mapping "NSE:RELIANCE" → {"last_price": ...}
        """
        self._require_connection()
        keys = [f"{exchange}:{s}" for s in instruments]
        return self._kite.ltp(keys)

    def get_historical(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str = "day",
    ):
        """Fetch historical OHLCV from Kite."""
        self._require_connection()
        return self._kite.historical_data(
            instrument_token, from_date, to_date, interval
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_quantity(
        self, signal: TradingSignal, portfolio_value: float
    ) -> int:
        target_value = portfolio_value * signal.position_pct
        ltp = self.get_ltp([signal.ticker], signal.market)
        price = ltp.get(f"{signal.market}:{signal.ticker}", {}).get(
            "last_price", 0
        )
        if price <= 0:
            return 0
        return max(0, int(target_value / price))

    def _paper_execute(
        self, signal: TradingSignal, portfolio_value: float
    ) -> str:
        fake_id = f"PAPER-{signal.ticker}-{signal.run_id}"
        log.info("kite.paper_order",
                 ticker=signal.ticker, signal=signal.signal,
                 position_pct=signal.position_pct,
                 order_id=fake_id)
        return fake_id

    def _require_connection(self) -> None:
        if self._kite is None:
            raise RuntimeError("Not connected. Call .connect() first.")
