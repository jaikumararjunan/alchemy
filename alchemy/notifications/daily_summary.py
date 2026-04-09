"""
alchemy.notifications.daily_summary
=====================================
Daily P&L summary cron — sends a Telegram/Slack summary at market close.

Scheduled times (configurable via env):
  - NSE/BSE/MCX: 3:35 PM IST (default)
  - Crypto: 11:59 PM UTC (24/7 markets)

Start from app lifespan::

    from alchemy.notifications.daily_summary import start_daily_summary_cron
    await start_daily_summary_cron()
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, time, timedelta
from typing import Optional

import structlog

from alchemy.notifications.dispatcher import dispatch
from alchemy.notifications.models import (
    EventSeverity, EventType, NotificationEvent,
)

log = structlog.get_logger(__name__)

# Configurable via env
SUMMARY_HOUR   = int(os.environ.get("DAILY_SUMMARY_HOUR", "15"))    # 3 PM
SUMMARY_MINUTE = int(os.environ.get("DAILY_SUMMARY_MINUTE", "35"))  # :35
TIMEZONE_STR   = os.environ.get("DAILY_SUMMARY_TZ", "Asia/Kolkata")

_task: Optional[asyncio.Task] = None


async def start_daily_summary_cron() -> None:
    """Start the daily summary background task."""
    global _task
    if _task and not _task.done():
        log.warning("daily_summary.already_running")
        return
    _task = asyncio.create_task(_cron_loop())
    log.info("daily_summary.cron_started",
             time=f"{SUMMARY_HOUR:02d}:{SUMMARY_MINUTE:02d}",
             tz=TIMEZONE_STR)


async def stop_daily_summary_cron() -> None:
    """Stop the daily summary background task."""
    global _task
    if _task:
        _task.cancel()
        _task = None
        log.info("daily_summary.cron_stopped")


async def _cron_loop() -> None:
    """Main cron loop — sleeps until next scheduled time, then fires."""
    while True:
        try:
            sleep_seconds = _seconds_until_next_run()
            log.debug("daily_summary.sleeping", seconds=sleep_seconds)
            await asyncio.sleep(sleep_seconds)
            await send_daily_summary()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("daily_summary.cron_error", error=str(e))
            await asyncio.sleep(60)  # Retry in 1 minute on error


def _seconds_until_next_run() -> float:
    """Calculate seconds until the next scheduled summary time."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(TIMEZONE_STR)
    except Exception:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("UTC")

    now = datetime.now(tz)
    target = now.replace(
        hour=SUMMARY_HOUR,
        minute=SUMMARY_MINUTE,
        second=0,
        microsecond=0,
    )

    if now >= target:
        target += timedelta(days=1)

    delta = (target - now).total_seconds()
    return max(delta, 1.0)


async def send_daily_summary() -> None:
    """
    Collect daily metrics and send summary notification.
    Called by cron or manually via API.
    """
    log.info("daily_summary.generating")

    try:
        metrics = await _collect_daily_metrics()
    except Exception as e:
        log.error("daily_summary.collect_error", error=str(e))
        metrics = _empty_metrics()

    # Format message
    pnl = metrics.get("realized_pnl", 0)
    pnl_sign = "+" if pnl >= 0 else ""
    trades = metrics.get("total_trades", 0)
    wins = metrics.get("winning_trades", 0)
    win_rate = (wins / trades * 100) if trades > 0 else 0
    open_positions = metrics.get("open_positions", 0)

    title = f"Daily P&L: {pnl_sign}${pnl:,.2f}"
    severity = EventSeverity.SUCCESS if pnl >= 0 else EventSeverity.WARNING

    message_parts = [
        f"Realized P&L: {pnl_sign}${pnl:,.2f}",
        f"Unrealized P&L: ${metrics.get('unrealized_pnl', 0):,.2f}",
        f"Total trades: {trades}",
        f"Winning: {wins} | Losing: {trades - wins}",
        f"Win rate: {win_rate:.1f}%",
        f"Open positions: {open_positions}",
    ]

    # Per-exchange breakdown
    for exchange, ex_data in metrics.get("by_exchange", {}).items():
        ex_pnl = ex_data.get("pnl", 0)
        ex_sign = "+" if ex_pnl >= 0 else ""
        message_parts.append(f"  {exchange}: {ex_sign}${ex_pnl:,.2f} ({ex_data.get('trades', 0)} trades)")

    if metrics.get("circuit_breaker_triggered"):
        message_parts.append("\nCircuit breaker was triggered today!")

    message = "\n".join(message_parts)

    try:
        await dispatch(NotificationEvent(
            event_type=EventType.DAILY_SUMMARY,
            severity=severity,
            title=title,
            message=message,
            data=metrics,
        ))
        log.info("daily_summary.sent", pnl=pnl, trades=trades)
    except Exception as e:
        log.error("daily_summary.send_error", error=str(e))


async def _collect_daily_metrics() -> dict:
    """
    Collect daily trading metrics from risk manager and exchange gateways.
    """
    metrics = _empty_metrics()

    # From risk manager
    try:
        from alchemy.risk.manager import RiskManager
        rm = RiskManager()
        status = rm.status()
        metrics["realized_pnl"] = status.get("daily_pnl", 0)
        metrics["open_positions"] = status.get("open_positions", 0)
        metrics["circuit_breaker_triggered"] = status.get("emergency_stop", False)
        metrics["max_drawdown"] = status.get("current_drawdown", 0)
    except Exception as e:
        log.warning("daily_summary.risk_manager_error", error=str(e))

    # From dedup stats
    try:
        from alchemy.risk.dedup import get_deduplicator
        dedup = get_deduplicator()
        metrics["dedup_stats"] = dedup.stats()
    except Exception:
        pass

    return metrics


def _empty_metrics() -> dict:
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "total_trades": 0,
        "winning_trades": 0,
        "open_positions": 0,
        "circuit_breaker_triggered": False,
        "max_drawdown": 0.0,
        "by_exchange": {},
        "dedup_stats": {},
    }
