"""
tests.unit.test_risk_modules
==============================
Integration tests for all risk safety modules:
  - OrderDeduplicator
  - PriceGuard
  - TradeAuditLog
  - ExchangeRateLimiter
"""
import asyncio
import json
import os
import tempfile
import time

import pytest


# ── OrderDeduplicator ─────────────────────────────────────────────────────────

class TestOrderDeduplicator:

    def setup_method(self):
        from alchemy.risk.dedup import OrderDeduplicator
        self.dedup = OrderDeduplicator(cooldown_seconds=2)

    def test_first_order_not_duplicate(self):
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY") is False

    def test_second_order_is_duplicate(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY") is True

    def test_different_symbol_not_duplicate(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        assert self.dedup.is_duplicate("sma", "ETHUSDT", "BUY") is False

    def test_different_side_not_duplicate(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "SELL") is False

    def test_cooldown_expires(self):
        from alchemy.risk.dedup import OrderDeduplicator
        self.dedup = OrderDeduplicator(cooldown_seconds=0)
        self.dedup.record("sma", "BTCUSDT", "BUY")
        time.sleep(0.05)
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY") is False

    def test_clear(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        count = self.dedup.clear()
        assert count == 1
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY") is False

    def test_stats(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        stats = self.dedup.stats()
        assert stats["total_entries"] == 1
        assert stats["cooldown_seconds"] == 2

    def test_cooldown_override(self):
        self.dedup.record("sma", "BTCUSDT", "BUY")
        # Default cooldown=2s should block
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY") is True
        # Override with 0s cooldown should pass
        assert self.dedup.is_duplicate("sma", "BTCUSDT", "BUY", cooldown_override=0) is False


# ── PriceGuard ────────────────────────────────────────────────────────────────

class TestPriceGuard:

    def setup_method(self):
        from alchemy.risk.price_guard import PriceGuard
        self.guard = PriceGuard(max_deviation_pct=5.0, stale_seconds=300)

    def test_no_reference_allows_order(self):
        result = self.guard.validate("UNKNOWN", 100.0)
        assert result.valid is True

    def test_within_threshold_passes(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        result = self.guard.validate("BTCUSDT", 62600.0)
        assert result.valid is True
        assert result.deviation_pct < 5.0

    def test_exceeds_threshold_rejected(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        result = self.guard.validate("BTCUSDT", 70000.0)  # 12% deviation
        assert result.valid is False
        assert "deviation" in result.reason.lower()

    def test_exact_price_passes(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        result = self.guard.validate("BTCUSDT", 62500.0)
        assert result.valid is True
        assert result.deviation_pct == 0.0

    def test_negative_price_rejected(self):
        result = self.guard.validate("BTCUSDT", -100.0)
        assert result.valid is False

    def test_zero_price_rejected(self):
        result = self.guard.validate("BTCUSDT", 0.0)
        assert result.valid is False

    def test_case_insensitive(self):
        self.guard.update_price("btcusdt", 62500.0)
        result = self.guard.validate("BTCUSDT", 62500.0)
        assert result.valid is True

    def test_stale_price_rejected(self):
        from alchemy.risk.price_guard import PriceGuard
        guard = PriceGuard(max_deviation_pct=5.0, stale_seconds=0)
        guard.update_price("BTCUSDT", 62500.0)
        time.sleep(0.05)
        result = guard.validate("BTCUSDT", 62500.0)
        assert result.valid is False
        assert "stale" in result.reason.lower()

    def test_stats(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        self.guard.update_price("ETHUSDT", 3400.0)
        stats = self.guard.stats()
        assert stats["total_symbols"] == 2
        assert stats["max_deviation_pct"] == 5.0

    def test_get_reference(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        ref = self.guard.get_reference("BTCUSDT")
        assert ref is not None
        assert ref["price"] == 62500.0

    def test_override_deviation(self):
        self.guard.update_price("BTCUSDT", 62500.0)
        # 4% deviation — fails at 3% override, passes at 5% default
        price = 62500.0 * 1.04
        result_strict = self.guard.validate("BTCUSDT", price, max_deviation_override=3.0)
        result_default = self.guard.validate("BTCUSDT", price)
        assert result_strict.valid is False
        assert result_default.valid is True


# ── TradeAuditLog ─────────────────────────────────────────────────────────────

class TestTradeAuditLog:

    def setup_method(self):
        from alchemy.risk.audit_log import TradeAuditLog
        self.tmpdir = tempfile.mkdtemp()
        self.log = TradeAuditLog(audit_dir=self.tmpdir)

    def test_record_and_recent(self):
        from alchemy.risk.audit_log import AuditEntry, AuditAction
        self.log.record(AuditEntry(
            action=AuditAction.ORDER_SUBMITTED,
            exchange="binance",
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.1,
            price=62500.0,
        ))
        recent = self.log.recent(limit=10)
        assert len(recent) == 1
        assert recent[0]["action"] == "order.submitted"
        assert recent[0]["symbol"] == "BTCUSDT"

    def test_file_durability(self):
        from alchemy.risk.audit_log import AuditEntry, AuditAction
        self.log.record(AuditEntry(
            action=AuditAction.KILL_SWITCH,
            user="admin",
            reason="test",
        ))
        # Read file directly
        filepath = os.path.join(self.tmpdir, "trade_audit.jsonl")
        with open(filepath) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["action"] == "kill_switch.activated"

    def test_log_signal_convenience(self):
        self.log.log_signal("sma_cross", "ETHUSDT", "SELL", confidence=0.85)
        recent = self.log.recent()
        assert recent[-1]["action"] == "signal.received"
        assert recent[-1]["metadata"]["confidence"] == 0.85

    def test_log_order_convenience(self):
        from alchemy.risk.audit_log import AuditAction
        self.log.log_order(
            AuditAction.ORDER_FILLED,
            exchange="delta",
            symbol="BTCUSD",
            side="BUY",
            quantity=1.0,
            price=62000.0,
            order_id="abc123",
        )
        recent = self.log.recent()
        assert recent[-1]["order_id"] == "abc123"

    def test_search_by_symbol(self):
        from alchemy.risk.audit_log import AuditEntry, AuditAction
        self.log.record(AuditEntry(action=AuditAction.ORDER_FILLED, symbol="BTCUSDT"))
        self.log.record(AuditEntry(action=AuditAction.ORDER_FILLED, symbol="ETHUSDT"))
        results = self.log.search(symbol="BTCUSDT")
        assert len(results) == 1

    def test_search_by_action(self):
        from alchemy.risk.audit_log import AuditEntry, AuditAction
        self.log.record(AuditEntry(action=AuditAction.ORDER_FILLED, symbol="BTC"))
        self.log.record(AuditEntry(action=AuditAction.KILL_SWITCH, symbol="BTC"))
        results = self.log.search(action="kill_switch.activated")
        assert len(results) == 1

    def test_stats(self):
        from alchemy.risk.audit_log import AuditEntry, AuditAction
        self.log.record(AuditEntry(action=AuditAction.ORDER_FILLED))
        self.log.record(AuditEntry(action=AuditAction.ORDER_FILLED))
        stats = self.log.stats()
        assert stats["total_entries"] == 2


# ── ExchangeRateLimiter ──────────────────────────────────────────────────────

class TestExchangeRateLimiter:

    def test_acquire_under_limit(self):
        from alchemy.execution.rate_limiter import ExchangeRateLimiter
        limiter = ExchangeRateLimiter("test", max_requests=100, window_seconds=1, burst_allowance=1.0)
        waited = asyncio.get_event_loop().run_until_complete(limiter.acquire())
        assert waited == 0.0

    def test_remaining_decreases(self):
        from alchemy.execution.rate_limiter import ExchangeRateLimiter
        limiter = ExchangeRateLimiter("test", max_requests=5, window_seconds=60, burst_allowance=1.0)
        asyncio.get_event_loop().run_until_complete(limiter.acquire())
        assert limiter.remaining == 4

    def test_stats(self):
        from alchemy.execution.rate_limiter import ExchangeRateLimiter
        limiter = ExchangeRateLimiter("binance", burst_allowance=1.0)
        stats = limiter.stats()
        assert stats["exchange"] == "binance"
        assert stats["max_requests"] == 1200
        assert stats["total_requests"] == 0

    def test_registry(self):
        from alchemy.execution.rate_limiter import get_rate_limiter, all_rate_limiter_stats
        limiter = get_rate_limiter("binance")
        assert limiter.exchange == "binance"
        stats = all_rate_limiter_stats()
        assert any(s["exchange"] == "binance" for s in stats)

    def test_weight(self):
        from alchemy.execution.rate_limiter import ExchangeRateLimiter
        limiter = ExchangeRateLimiter("test", max_requests=10, window_seconds=60, burst_allowance=1.0)
        asyncio.get_event_loop().run_until_complete(limiter.acquire(weight=3))
        assert limiter.current_usage == 3
        assert limiter.remaining == 7
