"""
alchemy.data.candle_validator
===============================
Candle data integrity validator.

Cross-checks WebSocket candle data against REST API data to detect:
  - Missing candles (gaps in the sequence)
  - Duplicate timestamps
  - OHLCV mismatches (drift between WS and REST feeds)
  - Stale feeds (no new candles received)

Run as a periodic background task or on-demand via API.

Usage::

    validator = CandleValidator()
    report = await validator.validate("BTCUSDT", "1m", source="binance")
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

MAX_ACCEPTABLE_DEVIATION_PCT = 0.01  # 0.01% OHLCV deviation threshold


@dataclass
class CandleIssue:
    """A single data integrity issue."""
    type: str        # "gap", "duplicate", "ohlcv_mismatch", "stale_feed"
    symbol: str
    timestamp: Optional[str] = None
    details: str = ""
    severity: str = "warning"  # "warning", "critical"


@dataclass
class ValidationReport:
    """Candle validation report for a single symbol."""
    symbol: str
    timeframe: str
    exchange: str
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    candles_checked: int = 0
    issues: list[CandleIssue] = field(default_factory=list)
    rest_candle_count: int = 0
    ws_candle_count: int = 0

    @property
    def clean(self) -> bool:
        return len(self.issues) == 0

    @property
    def critical_issues(self) -> list[CandleIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    def summary(self) -> str:
        status = "CLEAN" if self.clean else f"{len(self.issues)} ISSUES"
        lines = [
            f"{self.exchange}/{self.symbol} ({self.timeframe}): {status}",
            f"  REST candles: {self.rest_candle_count}",
            f"  WS candles:   {self.ws_candle_count}",
        ]
        for issue in self.issues[:5]:
            lines.append(f"  [{issue.type}] {issue.details}")
        if len(self.issues) > 5:
            lines.append(f"  ... and {len(self.issues) - 5} more")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "exchange": self.exchange,
            "validated_at": self.validated_at.isoformat(),
            "candles_checked": self.candles_checked,
            "clean": self.clean,
            "issue_count": len(self.issues),
            "critical_count": len(self.critical_issues),
            "rest_candle_count": self.rest_candle_count,
            "ws_candle_count": self.ws_candle_count,
            "issues": [
                {"type": i.type, "details": i.details, "severity": i.severity}
                for i in self.issues
            ],
        }


class CandleValidator:
    """
    Validates candle data integrity by comparing WebSocket and REST sources.
    """

    def __init__(
        self,
        deviation_threshold_pct: float = MAX_ACCEPTABLE_DEVIATION_PCT,
    ) -> None:
        self._threshold = deviation_threshold_pct / 100.0
        # In-memory candle buffer (populated by WS feed)
        self._ws_candles: dict[str, list[dict]] = {}

    def record_ws_candle(self, symbol: str, candle: dict) -> None:
        """
        Record a candle received via WebSocket.
        Call from your WS message handler.

        candle format: {"t": timestamp_ms, "o": open, "h": high, "l": low, "c": close, "v": volume}
        """
        key = symbol.upper()
        if key not in self._ws_candles:
            self._ws_candles[key] = []
        self._ws_candles[key].append(candle)

        # Keep last 500 candles per symbol
        if len(self._ws_candles[key]) > 500:
            self._ws_candles[key] = self._ws_candles[key][-500:]

    async def validate(
        self,
        symbol: str,
        timeframe: str = "1m",
        exchange: str = "binance",
        rest_candles: Optional[list[dict]] = None,
    ) -> ValidationReport:
        """
        Validate candle data for a symbol.

        If rest_candles is provided, uses those directly.
        Otherwise attempts to fetch via exchange REST API.
        """
        report = ValidationReport(
            symbol=symbol.upper(),
            timeframe=timeframe,
            exchange=exchange,
        )

        # Get REST candles
        if rest_candles is None:
            rest_candles = await self._fetch_rest_candles(symbol, timeframe, exchange)

        report.rest_candle_count = len(rest_candles)

        # Get WS candles
        ws_candles = self._ws_candles.get(symbol.upper(), [])
        report.ws_candle_count = len(ws_candles)

        if not rest_candles:
            report.issues.append(CandleIssue(
                type="no_rest_data",
                symbol=symbol,
                details="Could not fetch REST candles for comparison",
                severity="critical",
            ))
            return report

        # Validate REST candles internally (gaps, duplicates)
        self._check_gaps(rest_candles, report)
        self._check_duplicates(rest_candles, report)

        # Cross-validate WS vs REST if both available
        if ws_candles:
            self._cross_validate(ws_candles, rest_candles, report)

        # Check for stale feed
        self._check_staleness(ws_candles, report)

        report.candles_checked = len(rest_candles) + len(ws_candles)

        if not report.clean:
            log.warning("candle_validator.issues_found",
                        symbol=symbol, count=len(report.issues))
            # Notify if critical
            if report.critical_issues:
                await self._notify(report)

        return report

    def _check_gaps(self, candles: list[dict], report: ValidationReport) -> None:
        """Check for gaps in candle timestamps."""
        if len(candles) < 2:
            return

        for i in range(1, len(candles)):
            t_prev = candles[i - 1].get("t", 0)
            t_curr = candles[i].get("t", 0)
            if t_prev == 0 or t_curr == 0:
                continue

            # Expected interval (auto-detect from first two candles)
            if i == 1:
                expected_interval = t_curr - t_prev
                if expected_interval <= 0:
                    continue
            else:
                gap = t_curr - t_prev
                if gap > expected_interval * 1.5:
                    missing_count = int(gap / expected_interval) - 1
                    report.issues.append(CandleIssue(
                        type="gap",
                        symbol=report.symbol,
                        timestamp=str(t_prev),
                        details=f"Gap of {missing_count} candle(s) between "
                                f"{t_prev} and {t_curr}",
                        severity="critical" if missing_count > 5 else "warning",
                    ))

    def _check_duplicates(self, candles: list[dict], report: ValidationReport) -> None:
        """Check for duplicate timestamps."""
        seen: set = set()
        for c in candles:
            t = c.get("t", 0)
            if t in seen:
                report.issues.append(CandleIssue(
                    type="duplicate",
                    symbol=report.symbol,
                    timestamp=str(t),
                    details=f"Duplicate candle at timestamp {t}",
                ))
            seen.add(t)

    def _cross_validate(
        self,
        ws_candles: list[dict],
        rest_candles: list[dict],
        report: ValidationReport,
    ) -> None:
        """Cross-validate WS candles against REST candles."""
        # Index REST candles by timestamp
        rest_by_ts = {c.get("t"): c for c in rest_candles if c.get("t")}

        matched = 0
        for ws_c in ws_candles:
            ts = ws_c.get("t")
            if ts not in rest_by_ts:
                continue

            rest_c = rest_by_ts[ts]
            matched += 1

            # Compare OHLCV
            for field_name in ("o", "h", "l", "c", "v"):
                ws_val = float(ws_c.get(field_name, 0))
                rest_val = float(rest_c.get(field_name, 0))
                if rest_val == 0:
                    continue

                deviation = abs(ws_val - rest_val) / rest_val
                if deviation > self._threshold:
                    report.issues.append(CandleIssue(
                        type="ohlcv_mismatch",
                        symbol=report.symbol,
                        timestamp=str(ts),
                        details=f"{field_name.upper()}: WS={ws_val}, REST={rest_val}, "
                                f"deviation={deviation*100:.4f}%",
                        severity="warning",
                    ))

    def _check_staleness(
        self, ws_candles: list[dict], report: ValidationReport,
    ) -> None:
        """Check if WS feed is stale (no recent candles)."""
        if not ws_candles:
            report.issues.append(CandleIssue(
                type="stale_feed",
                symbol=report.symbol,
                details="No WebSocket candles in buffer — feed may be disconnected",
                severity="critical",
            ))
            return

        latest = max(c.get("t", 0) for c in ws_candles)
        if latest > 0:
            # If latest candle is >5 min old, flag as stale
            age_s = time.time() - (latest / 1000 if latest > 1e12 else latest)
            if age_s > 300:
                report.issues.append(CandleIssue(
                    type="stale_feed",
                    symbol=report.symbol,
                    details=f"Latest WS candle is {age_s:.0f}s old (>300s threshold)",
                    severity="critical",
                ))

    async def _fetch_rest_candles(
        self, symbol: str, timeframe: str, exchange: str,
    ) -> list[dict]:
        """Fetch candles via exchange REST API. Returns empty list on failure."""
        # TODO: Wire into your exchange gateways
        # Example for Binance:
        #   from alchemy.execution.crypto.binance_gateway import BinanceGateway
        #   gw = BinanceGateway()
        #   return await gw.get_klines(symbol, timeframe, limit=100)
        log.debug("candle_validator.fetch_rest_stub",
                  symbol=symbol, exchange=exchange)
        return []

    async def _notify(self, report: ValidationReport) -> None:
        """Send notification for critical data issues."""
        try:
            from alchemy.notifications.dispatcher import dispatch
            from alchemy.notifications.models import (
                EventSeverity, EventType, NotificationEvent,
            )
            await dispatch(NotificationEvent(
                event_type=EventType.SYSTEM_ERROR,
                severity=EventSeverity.WARNING,
                title=f"Candle Data Issue: {report.symbol}",
                message=report.summary(),
                data=report.to_dict(),
            ))
        except Exception as e:
            log.error("candle_validator.notify_error", error=str(e))


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[CandleValidator] = None


def get_candle_validator() -> CandleValidator:
    global _instance
    if _instance is None:
        _instance = CandleValidator()
    return _instance
