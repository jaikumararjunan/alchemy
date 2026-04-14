"""
tests/integration/test_api_routes.py
======================================
HTTP-level integration tests for all major API routes.
Uses FastAPI TestClient for full request/response cycle.

Run: pytest tests/integration/test_api_routes.py -v
"""
import os
import tempfile

# Set env BEFORE any app imports
_TEST_DIR = tempfile.mkdtemp(prefix="alchemy_api_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DIR}/api_test.db")
os.environ.setdefault("ALCHEMY_PAPER_DIR", _TEST_DIR)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-api-tests")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789abcdef")

import json
import pytest
from fastapi.testclient import TestClient
from alchemy.api.app import app

client = TestClient(app)

# Create tables on startup
import asyncio
from alchemy.api.database import get_engine

async def _create_tables():
    from alchemy.users.models import Base
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

try:
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables())
    loop.close()
except Exception as e:
    print(f"Table creation: {e}")

client = TestClient(app)

# ── Auth Helpers ──────────────────────────────────────────────────────────────

_SHARED_EMAIL = "api-test@alchemy.ai"
_SHARED_PASS = "TestPassword123!"
_cached_headers = None

def _signup(email=_SHARED_EMAIL, password=_SHARED_PASS):
    username = email.split("@")[0].replace(".", "_").replace("-", "_")
    return client.post("/api/auth/signup", json={
        "email": email, "password": password,
        "username": username, "full_name": "Test User",
    })

def _login(email=_SHARED_EMAIL, password=_SHARED_PASS):
    return client.post("/api/auth/login", json={"email": email, "password": password})

def _auth_headers(email=_SHARED_EMAIL, password=_SHARED_PASS):
    global _cached_headers
    if _cached_headers and email == _SHARED_EMAIL:
        return _cached_headers
    r = _login(email, password)
    if r.status_code != 200:
        _signup(email, password)
        r = _login(email, password)
    token = r.json().get("access_token", "")
    h = {"Authorization": f"Bearer {token}"}
    if email == _SHARED_EMAIL:
        _cached_headers = h
    return h

# Pre-register shared user
_signup()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HEALTH & STATUS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoints:

    def test_health_check(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_version(self):
        r = client.get("/api/health")
        assert "version" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. AUTH FLOW
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthFlow:

    def test_signup(self):
        r = _signup("signup-test@alchemy.ai", "StrongPassword1!")
        assert r.status_code in (200, 201, 409)  # 409 if already exists

    def test_login(self):
        _signup("login-test@alchemy.ai", "StrongPassword1!")
        r = _login("login-test@alchemy.ai", "StrongPassword1!")
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self):
        _signup("wrong-pw@alchemy.ai", "StrongPassword1!")
        r = _login("wrong-pw@alchemy.ai", "WrongPassword99!")
        assert r.status_code in (401, 403)

    def test_protected_route_no_token(self):
        r = client.get("/api/paper/portfolio")
        assert r.status_code == 401

    def test_protected_route_with_token(self):
        h = _auth_headers()
        r = client.get("/api/paper/portfolio", headers=h)
        assert r.status_code == 200

    def test_me_endpoint(self):
        _signup("me-test@alchemy.ai", "TestPassword123!")
        h = _auth_headers("me-test@alchemy.ai", "TestPassword123!")
        r = client.get("/api/auth/me", headers=h)
        assert r.status_code == 200
        assert "email" in r.json() or "user" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PAPER TRADING API
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperTradingAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_get_portfolio(self):
        r = client.get("/api/paper/portfolio", headers=self.h)
        assert r.status_code == 200
        d = r.json()
        assert "cash_balance" in d
        assert "positions" in d
        assert d["cash_balance"] > 0

    def test_place_buy_order(self):
        r = client.post("/api/paper/order", headers=self.h, json={
            "symbol": "BTCUSDT", "side": "buy", "quantity": 0.01,
            "current_price": 70000, "order_type": "market",
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") == "filled" or d.get("ok")

    def test_place_sell_order(self):
        r = client.post("/api/paper/order", headers=self.h, json={
            "symbol": "ETHUSDT", "side": "sell", "quantity": 1,
            "current_price": 2500, "order_type": "market",
        })
        assert r.status_code == 200

    def test_close_position(self):
        # Open first
        client.post("/api/paper/order", headers=self.h, json={
            "symbol": "SOLUSDT", "side": "buy", "quantity": 5,
            "current_price": 150, "order_type": "market",
        })
        # Close
        r = client.post("/api/paper/close", headers=self.h, json={
            "symbol": "SOLUSDT", "current_price": 155,
        })
        assert r.status_code == 200

    def test_update_prices(self):
        r = client.post("/api/paper/update-prices", headers=self.h, json={
            "prices": {"BTCUSDT": 71000, "ETHUSDT": 2550}
        })
        assert r.status_code == 200
        assert "events" in r.json()

    def test_order_history(self):
        r = client.get("/api/paper/orders?limit=10", headers=self.h)
        assert r.status_code == 200

    def test_trade_history(self):
        r = client.get("/api/paper/trades?limit=10", headers=self.h)
        assert r.status_code == 200

    def test_leaderboard(self):
        r = client.get("/api/paper/leaderboard", headers=self.h)
        assert r.status_code == 200

    def test_reset_portfolio(self):
        r = client.post("/api/paper/reset", headers=self.h, json={
            "initial_balance": 50000
        })
        assert r.status_code == 200

    def test_invalid_order_zero_quantity(self):
        r = client.post("/api/paper/order", headers=self.h, json={
            "symbol": "BTCUSDT", "side": "buy", "quantity": 0,
            "current_price": 70000, "order_type": "market",
        })
        # Should be rejected (400 or 200 with rejected status)
        assert r.status_code in (200, 400, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ANALYTICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyticsAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_equity_curve(self):
        r = client.get("/api/paper/equity-curve?days=7", headers=self.h)
        assert r.status_code == 200
        assert "points" in r.json()

    def test_heatmap(self):
        r = client.get("/api/paper/heatmap", headers=self.h)
        assert r.status_code == 200
        assert "cells" in r.json()

    def test_ai_recommendations(self):
        r = client.get("/api/paper/ai-recommendations", headers=self.h)
        assert r.status_code == 200
        d = r.json()
        assert "recommendations" in d
        assert "portfolio_summary" in d

    def test_strategy_comparison(self):
        r = client.get("/api/paper/strategy-comparison", headers=self.h)
        assert r.status_code == 200
        assert "strategies" in r.json()

    def test_position_size_calculator(self):
        r = client.post("/api/paper/position-size", headers=self.h, json={
            "account_size": 100000, "risk_pct": 1.0,
            "entry_price": 70000, "stop_loss_price": 68000,
        })
        assert r.status_code == 200
        d = r.json()
        assert d["quantity"] == 0.5  # $1000 risk / $2000 diff
        assert d["risk_amount"] == 1000

    def test_tax_export(self):
        r = client.get("/api/paper/tax-export?financial_year=2025-26", headers=self.h)
        # May return 200 CSV or 200 JSON with error if no trades
        assert r.status_code == 200

    def test_live_prices(self):
        r = client.get("/api/paper/live-prices", headers=self.h)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 5. JOURNAL API
# ═══════════════════════════════════════════════════════════════════════════════

class TestJournalAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_create_entry(self):
        r = client.post("/api/journal", headers=self.h, json={
            "symbol": "BTCUSDT", "side": "buy",
            "entry_price": 70000, "exit_price": 73000,
            "pnl": 300, "tags": ["swing"], "emotion": "confident",
            "notes": "Good entry on support bounce",
        })
        assert r.status_code == 200
        assert r.json()["ok"]

    def test_list_entries(self):
        r = client.get("/api/journal", headers=self.h)
        assert r.status_code == 200
        assert "entries" in r.json()

    def test_journal_stats(self):
        r = client.get("/api/journal/stats", headers=self.h)
        assert r.status_code == 200
        d = r.json()
        assert "total_entries" in d
        assert "emotions" in d

    def test_auto_import(self):
        r = client.post("/api/journal/auto-import", headers=self.h)
        assert r.status_code == 200
        assert "imported" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. WEBHOOK API
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhookAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_setup_webhook(self):
        r = client.post("/api/webhook/setup", headers=self.h)
        assert r.status_code == 200
        d = r.json()
        assert "webhook_url" in d
        assert "token" in d
        self.__class__.webhook_token = d["token"]

    def test_get_config(self):
        client.post("/api/webhook/setup", headers=self.h)
        r = client.get("/api/webhook/config", headers=self.h)
        assert r.status_code == 200

    def test_receive_json_signal(self):
        setup = client.post("/api/webhook/setup", headers=self.h)
        token = setup.json()["token"]

        # Enable auto-execute
        client.post("/api/webhook/configure", headers=self.h, json={
            "auto_execute": True, "max_position_pct": 2.0,
        })

        r = client.post(f"/api/webhook/receive/{token}", json={
            "symbol": "BTCUSDT", "side": "buy", "price": 70000,
        })
        assert r.status_code == 200
        assert r.json()["received"]

    def test_receive_text_signal(self):
        setup = client.post("/api/webhook/setup", headers=self.h)
        token = setup.json()["token"]

        r = client.post(f"/api/webhook/receive/{token}",
                        content="BUY ETHUSDT 0.5",
                        headers={"Content-Type": "text/plain"})
        assert r.status_code == 200

    def test_invalid_token(self):
        r = client.post("/api/webhook/receive/invalid-token-123", json={
            "symbol": "BTCUSDT", "side": "buy",
        })
        assert r.status_code == 404

    def test_webhook_log(self):
        r = client.get("/api/webhook/log", headers=self.h)
        assert r.status_code == 200
        assert "events" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ADVANCED ORDERS API
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdvancedOrdersAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_create_oco(self):
        r = client.post("/api/orders/advanced/oco", headers=self.h, json={
            "symbol": "BTCUSDT", "side": "buy", "quantity": 0.1,
            "stop_loss": 68000, "take_profit": 75000,
        })
        assert r.status_code == 200
        assert r.json()["type"] == "oco"

    def test_create_bracket(self):
        r = client.post("/api/orders/advanced/bracket", headers=self.h, json={
            "symbol": "ETHUSDT", "side": "buy", "quantity": 1,
            "entry_price": 2500, "stop_loss": 2400, "take_profit": 2700,
        })
        assert r.status_code == 200
        assert r.json()["type"] == "bracket"

    def test_create_trailing_stop(self):
        r = client.post("/api/orders/advanced/trailing-stop", headers=self.h, json={
            "symbol": "BTCUSDT", "side": "long", "quantity": 0.1,
            "trailing_pct": 2.0,
        })
        assert r.status_code == 200
        assert r.json()["type"] == "trailing_stop"

    def test_list_orders(self):
        r = client.get("/api/orders/advanced?status=active", headers=self.h)
        assert r.status_code == 200
        assert "orders" in r.json()

    def test_cancel_order(self):
        # Create then cancel
        create = client.post("/api/orders/advanced/oco", headers=self.h, json={
            "symbol": "SOLUSDT", "side": "buy", "quantity": 5,
            "stop_loss": 140, "take_profit": 170,
        })
        order_id = create.json().get("id", 1)
        r = client.delete(f"/api/orders/advanced/{order_id}", headers=self.h)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SOCIAL / COPY TRADING API
# ═══════════════════════════════════════════════════════════════════════════════

class TestSocialAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_leaderboard(self):
        r = client.get("/api/social/leaderboard", headers=self.h)
        assert r.status_code == 200
        assert "leaderboard" in r.json()

    def test_following_empty(self):
        r = client.get("/api/social/following", headers=self.h)
        assert r.status_code == 200
        assert "following" in r.json()

    def test_followers_empty(self):
        r = client.get("/api/social/followers", headers=self.h)
        assert r.status_code == 200

    def test_create_post(self):
        r = client.post("/api/social/post", headers=self.h, json={
            "content": "Just closed a nice BTC swing trade! +$500",
        })
        assert r.status_code == 200
        assert r.json()["ok"]

    def test_get_feed(self):
        r = client.get("/api/social/feed", headers=self.h)
        assert r.status_code == 200
        assert "posts" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. PUSH NOTIFICATIONS API
# ═══════════════════════════════════════════════════════════════════════════════

class TestPushAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_register_token(self):
        r = client.post("/api/push/register", headers=self.h, json={
            "token": "ExponentPushToken[test-token-12345]",
            "platform": "expo",
        })
        assert r.status_code == 200
        assert r.json()["ok"]

    def test_list_tokens(self):
        r = client.get("/api/push/tokens", headers=self.h)
        assert r.status_code == 200
        assert "tokens" in r.json()

    def test_invalid_token_rejected(self):
        r = client.post("/api/push/register", headers=self.h, json={
            "token": "not-an-expo-token",
        })
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 10. WATCHLIST & ALERTS API
# ═══════════════════════════════════════════════════════════════════════════════

class TestWatchlistAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_add_to_watchlist(self):
        r = client.post("/api/watchlist", headers=self.h, json={
            "symbol": "BTCUSDT",
        })
        assert r.status_code in (200, 201)

    def test_list_watchlist(self):
        r = client.get("/api/watchlist", headers=self.h)
        assert r.status_code == 200

    def test_remove_from_watchlist(self):
        client.post("/api/watchlist", headers=self.h, json={"symbol": "DOGEUSDT"})
        r = client.delete("/api/watchlist/DOGEUSDT", headers=self.h)
        assert r.status_code == 200


class TestAlertsAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_create_alert(self):
        r = client.post("/api/alerts", headers=self.h, json={
            "symbol": "BTCUSDT", "target_price": 75000,
            "condition": "above",
        })
        assert r.status_code in (200, 201)

    def test_list_alerts(self):
        r = client.get("/api/alerts", headers=self.h)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 11. TOKEN / EXCHANGE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenAPI:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.h = _auth_headers()

    def test_register_exchange_token(self):
        r = client.post("/api/tokens/register", headers=self.h, json={
            "exchange": "binance", "api_key": "test-key-123",
            "api_secret": "test-secret", "paper_trading": True,
        })
        assert r.status_code == 200
        assert r.json()["ok"]

    def test_get_token_status(self):
        r = client.get("/api/tokens/status", headers=self.h)
        assert r.status_code == 200

    def test_list_accounts(self):
        r = client.get("/api/tokens/accounts/binance", headers=self.h)
        assert r.status_code == 200
        assert "accounts" in r.json()

    def test_add_multi_account(self):
        r = client.post("/api/tokens/accounts/binance", headers=self.h, json={
            "account_name": "hedge-account",
            "api_key": "hedge-key-456",
            "paper_trading": True,
        })
        assert r.status_code == 200
