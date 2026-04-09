"""
alchemy.trading.session_manager
=================================
Market session manager — knows when each exchange is open,
auto-halts trading outside hours, handles pre-market/post-market.

Supports:
  - NSE/BSE: 9:15 AM - 3:30 PM IST (Mon-Fri, excluding holidays)
  - MCX:     9:00 AM - 11:30 PM IST (Mon-Fri)
  - Crypto:  24/7 (Binance, Delta)

Usage::

    from alchemy.trading.session_manager import get_session_manager

    mgr = get_session_manager()
    if mgr.is_market_open("nse"):
        # Place order
    else:
        info = mgr.next_open("nse")
        print(f"NSE opens in {info['hours_until_open']}h")
"""
from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Optional
from enum import Enum

import structlog

log = structlog.get_logger(__name__)


class Market(str, Enum):
    NSE    = "nse"
    BSE    = "bse"
    MCX    = "mcx"
    BINANCE = "binance"
    DELTA  = "delta"
    ANGEL  = "angel"
    KITE   = "kite"


# Indian market holidays 2026 (add/update annually)
INDIA_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 10),   # Maha Shivaratri
    date(2026, 3, 17),   # Holi
    date(2026, 3, 30),   # Id-ul-Fitr
    date(2026, 4, 2),    # Ram Navami
    date(2026, 4, 6),    # Mahavir Jayanti
    date(2026, 4, 10),   # Good Friday
    date(2026, 4, 14),   # Dr Ambedkar Jayanti
    date(2026, 5, 1),    # May Day
    date(2026, 6, 6),    # Id-ul-Adha
    date(2026, 7, 6),    # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 9, 4),    # Milad-un-Nabi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 9),   # Diwali (Laxmi Puja)
    date(2026, 11, 10),  # Diwali Balipratipada
    date(2026, 11, 30),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}

# Session times (IST)
SESSIONS = {
    Market.NSE: {
        "pre_open_start": time(9, 0),
        "open": time(9, 15),
        "close": time(15, 30),
        "post_close": time(16, 0),
        "is_24_7": False,
        "holidays": INDIA_HOLIDAYS_2026,
    },
    Market.BSE: {
        "pre_open_start": time(9, 0),
        "open": time(9, 15),
        "close": time(15, 30),
        "post_close": time(16, 0),
        "is_24_7": False,
        "holidays": INDIA_HOLIDAYS_2026,
    },
    Market.MCX: {
        "open": time(9, 0),
        "close": time(23, 30),
        "is_24_7": False,
        "holidays": INDIA_HOLIDAYS_2026,
    },
    Market.BINANCE: {
        "is_24_7": True,
    },
    Market.DELTA: {
        "is_24_7": True,
    },
    Market.ANGEL: {
        "pre_open_start": time(9, 0),
        "open": time(9, 15),
        "close": time(15, 30),
        "is_24_7": False,
        "holidays": INDIA_HOLIDAYS_2026,
    },
    Market.KITE: {
        "pre_open_start": time(9, 0),
        "open": time(9, 15),
        "close": time(15, 30),
        "is_24_7": False,
        "holidays": INDIA_HOLIDAYS_2026,
    },
}

# Map exchange names to markets
EXCHANGE_MARKET_MAP = {
    "binance": Market.BINANCE,
    "delta": Market.DELTA,
    "angel": Market.ANGEL,
    "kite": Market.KITE,
    "nse": Market.NSE,
    "bse": Market.BSE,
    "mcx": Market.MCX,
}


def _ist_now() -> datetime:
    """Get current time in IST."""
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    except Exception:
        # Fallback: UTC + 5:30
        from datetime import timezone
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist)


class SessionManager:
    """
    Manages market trading sessions across all supported exchanges.
    """

    def is_market_open(self, exchange: str) -> bool:
        """Check if a market/exchange is currently open for trading."""
        market = EXCHANGE_MARKET_MAP.get(exchange.lower())
        if not market:
            return True  # Unknown exchange — assume open

        session = SESSIONS.get(market, {})
        if session.get("is_24_7"):
            return True

        now = _ist_now()

        # Weekend check (Mon=0, Sun=6)
        if now.weekday() >= 5:
            return False

        # Holiday check
        holidays = session.get("holidays", set())
        if now.date() in holidays:
            return False

        # Time check
        market_open = session.get("open", time(9, 15))
        market_close = session.get("close", time(15, 30))
        current_time = now.time()

        return market_open <= current_time <= market_close

    def is_pre_market(self, exchange: str) -> bool:
        """Check if we're in pre-market session."""
        market = EXCHANGE_MARKET_MAP.get(exchange.lower())
        if not market:
            return False

        session = SESSIONS.get(market, {})
        if session.get("is_24_7"):
            return False

        now = _ist_now()
        if now.weekday() >= 5:
            return False

        pre_open = session.get("pre_open_start")
        market_open = session.get("open")
        if pre_open and market_open:
            return pre_open <= now.time() < market_open
        return False

    def next_open(self, exchange: str) -> dict:
        """Get info about the next market open."""
        market = EXCHANGE_MARKET_MAP.get(exchange.lower())
        if not market:
            return {"is_open": True}

        session = SESSIONS.get(market, {})
        if session.get("is_24_7"):
            return {"is_open": True, "market": market.value}

        now = _ist_now()
        market_open = session.get("open", time(9, 15))
        market_close = session.get("close", time(15, 30))
        holidays = session.get("holidays", set())

        # If currently open
        if self.is_market_open(exchange):
            close_dt = now.replace(
                hour=market_close.hour, minute=market_close.minute, second=0
            )
            remaining = (close_dt - now).total_seconds() / 3600
            return {
                "is_open": True,
                "market": market.value,
                "closes_in_hours": round(remaining, 2),
                "close_time": market_close.strftime("%H:%M IST"),
            }

        # Find next trading day
        check_date = now.date()
        if now.time() > market_close:
            check_date += timedelta(days=1)

        for _ in range(10):  # Max 10 days lookahead
            if check_date.weekday() < 5 and check_date not in holidays:
                break
            check_date += timedelta(days=1)

        next_open_dt = datetime.combine(check_date, market_open)
        try:
            import zoneinfo
            next_open_dt = next_open_dt.replace(
                tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")
            )
        except Exception:
            pass

        hours_until = (next_open_dt - now).total_seconds() / 3600

        return {
            "is_open": False,
            "market": market.value,
            "next_open_date": check_date.isoformat(),
            "next_open_time": market_open.strftime("%H:%M IST"),
            "hours_until_open": round(max(0, hours_until), 2),
        }

    def all_sessions_status(self) -> list[dict]:
        """Get status for all markets."""
        results = []
        seen = set()
        for exchange, market in EXCHANGE_MARKET_MAP.items():
            if market.value in seen:
                continue
            seen.add(market.value)
            info = self.next_open(exchange)
            info["exchange"] = exchange
            results.append(info)
        return results

    def should_trade(self, exchange: str, allow_pre_market: bool = False) -> tuple[bool, str]:
        """
        Check if trading should be allowed right now.
        Returns (allowed, reason).
        """
        if self.is_market_open(exchange):
            return True, "Market is open"
        if allow_pre_market and self.is_pre_market(exchange):
            return True, "Pre-market session"
        info = self.next_open(exchange)
        return False, f"Market closed. Opens {info.get('next_open_date', '?')} at {info.get('next_open_time', '?')}"


# Singleton
_instance: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    global _instance
    if _instance is None:
        _instance = SessionManager()
    return _instance
