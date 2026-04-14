"""
tests/conftest.py
==================
Shared fixtures for Alchemy test suite.
"""
import os
import sys
import json
import tempfile
import pytest

# Set test env vars BEFORE any app imports
TEST_DIR = tempfile.mkdtemp(prefix="alchemy_test_")
os.environ["ALCHEMY_PAPER_DIR"] = TEST_DIR
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DIR}/test_alchemy.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only-0123456789"
os.environ["JWT_SECRET"] = "test-jwt-secret-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _reset_engine():
    """Reset paper engine singleton between tests."""
    import alchemy.paper_trading.engine as eng
    eng._engine = None
    yield
    eng._engine = None


@pytest.fixture
def engine():
    from alchemy.paper_trading.engine import get_paper_engine
    return get_paper_engine()


@pytest.fixture
def user_id():
    return "test-user-e2e-001"


@pytest.fixture
def portfolio(engine, user_id):
    return engine.get_portfolio(user_id)


@pytest.fixture
def funded_long(engine, user_id):
    """User with an open LONG BTCUSDT position."""
    engine.place_order(user_id, "BTCUSDT", "buy", 0.5, 70000, order_type="market")
    return engine.get_portfolio(user_id)


@pytest.fixture
def funded_short(engine, user_id):
    """User with an open SHORT ETHUSDT position."""
    engine.place_order(user_id, "ETHUSDT", "sell", 10, 2500, order_type="market")
    return engine.get_portfolio(user_id)


@pytest.fixture
def multi_position(engine, user_id):
    """User with 3 open positions."""
    engine.place_order(user_id, "BTCUSDT", "buy", 0.2, 70000, order_type="market")
    engine.place_order(user_id, "ETHUSDT", "buy", 5, 2500, order_type="market")
    engine.place_order(user_id, "SOLUSDT", "sell", 50, 150, order_type="market")
    return engine.get_portfolio(user_id)


@pytest.fixture
def closed_trades(engine, user_id):
    """User with 3 closed trades (2 wins, 1 loss)."""
    engine.place_order(user_id, "BTCUSDT", "buy", 0.1, 70000, order_type="market")
    engine.close_position(user_id, "BTCUSDT", current_price=73000)  # +3K

    engine.place_order(user_id, "ETHUSDT", "buy", 2, 2500, order_type="market")
    engine.close_position(user_id, "ETHUSDT", current_price=2600)   # +200

    engine.place_order(user_id, "SOLUSDT", "buy", 10, 150, order_type="market")
    engine.close_position(user_id, "SOLUSDT", current_price=140)    # -100

    return engine.get_portfolio(user_id)
