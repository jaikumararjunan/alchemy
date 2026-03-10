"""
Real-time WebSocket price monitor for Delta Exchange.
Monitors prices, triggers trailing stop updates, and sends alerts.
"""
import json
import asyncio
import threading
import time
from typing import Callable, Dict, Optional
from dataclasses import dataclass

import websocket

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PriceUpdate:
    symbol: str
    price: float
    timestamp: float
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class TrailingStop:
    symbol: str
    side: str       # "long" or "short"
    entry_price: float
    initial_stop: float
    current_stop: float
    trail_pct: float   # e.g. 0.015 = 1.5%
    peak_price: float  # highest (long) or lowest (short) seen


class DeltaWSMonitor:
    """
    WebSocket price monitor that:
    1. Subscribes to real-time ticker data
    2. Maintains trailing stops
    3. Triggers callbacks on price updates and stop triggers
    """

    WS_URL = "wss://socket.india.delta.exchange"

    def __init__(self, symbols: list, on_price: Callable = None, on_stop_trigger: Callable = None):
        self.symbols = symbols
        self.on_price = on_price
        self.on_stop_trigger = on_stop_trigger
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._prices: Dict[str, PriceUpdate] = {}
        self._trailing_stops: Dict[str, TrailingStop] = {}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"WebSocket monitor started for: {self.symbols}")

    def stop(self):
        self._running = False
        if self._ws:
            self._ws.close()
        logger.info("WebSocket monitor stopped")

    def add_trailing_stop(self, symbol: str, side: str, entry_price: float,
                          stop_price: float, trail_pct: float = 0.015):
        self._trailing_stops[symbol] = TrailingStop(
            symbol=symbol, side=side, entry_price=entry_price,
            initial_stop=stop_price, current_stop=stop_price,
            trail_pct=trail_pct, peak_price=entry_price,
        )
        logger.info(f"Trailing stop set: {symbol} {side} entry={entry_price} stop={stop_price} trail={trail_pct*100}%")

    def remove_trailing_stop(self, symbol: str):
        if symbol in self._trailing_stops:
            del self._trailing_stops[symbol]
            logger.info(f"Trailing stop removed: {symbol}")

    def get_price(self, symbol: str) -> Optional[float]:
        update = self._prices.get(symbol)
        return update.price if update else None

    def _run(self):
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    self.WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            if self._running:
                logger.info("WebSocket reconnecting in 5s...")
                time.sleep(5)

    def _on_open(self, ws):
        logger.info("WebSocket connected to Delta Exchange")
        # Subscribe to mark_price and spot_price channels
        for sym in self.symbols:
            subscribe_msg = {
                "type": "subscribe",
                "payload": {
                    "channels": [
                        {"name": "mark_price", "symbols": [sym]},
                        {"name": "spot_price", "symbols": [sym]},
                    ]
                }
            }
            ws.send(json.dumps(subscribe_msg))

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type in ("mark_price", "spot_price"):
                sym = data.get("symbol")
                price = float(data.get("price", 0))
                if sym and price > 0:
                    update = PriceUpdate(
                        symbol=sym, price=price, timestamp=time.time()
                    )
                    self._prices[sym] = update

                    if self.on_price:
                        self.on_price(update)

                    # Check trailing stops
                    self._check_trailing_stop(sym, price)

        except Exception as e:
            logger.debug(f"WS message parse error: {e}")

    def _check_trailing_stop(self, symbol: str, price: float):
        ts = self._trailing_stops.get(symbol)
        if not ts:
            return

        triggered = False
        new_stop = ts.current_stop

        if ts.side == "long":
            # Update peak and trail stop up
            if price > ts.peak_price:
                ts.peak_price = price
                potential_stop = price * (1 - ts.trail_pct)
                if potential_stop > ts.current_stop:
                    new_stop = potential_stop
                    ts.current_stop = new_stop
                    logger.info(f"Trailing stop raised: {symbol} long -> ${new_stop:.2f} (price=${price:.2f})")

            # Check if price hit stop
            if price <= ts.current_stop:
                triggered = True
                logger.warning(f"TRAILING STOP TRIGGERED: {symbol} long at ${price:.2f} (stop=${ts.current_stop:.2f})")

        elif ts.side == "short":
            if price < ts.peak_price:
                ts.peak_price = price
                potential_stop = price * (1 + ts.trail_pct)
                if potential_stop < ts.current_stop:
                    new_stop = potential_stop
                    ts.current_stop = new_stop

            if price >= ts.current_stop:
                triggered = True
                logger.warning(f"TRAILING STOP TRIGGERED: {symbol} short at ${price:.2f} (stop=${ts.current_stop:.2f})")

        if triggered and self.on_stop_trigger:
            self.on_stop_trigger(ts, price)
            del self._trailing_stops[symbol]

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, code, msg):
        logger.info(f"WebSocket closed: {code} {msg}")
