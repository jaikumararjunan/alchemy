"""tests/unit/workflows/test_token_workflow.py"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ── TokenVault ────────────────────────────────────────────────────────────────
class TestTokenVault:
    def test_store_retrieve_no_crypto(self, tmp_path):
        from alchemy.tokens.vault import TokenVault
        vault = TokenVault(vault_dir=tmp_path)
        vault.store("delta", {"api_key": "abc123", "status": "active"})
        data = vault.retrieve("delta")
        assert data is not None
        assert data["api_key"] == "abc123"

    def test_delete(self, tmp_path):
        from alchemy.tokens.vault import TokenVault
        vault = TokenVault(vault_dir=tmp_path)
        vault.store("kite", {"test": True})
        assert vault.delete("kite") is True
        assert vault.retrieve("kite") is None

    def test_list_exchanges(self, tmp_path):
        from alchemy.tokens.vault import TokenVault
        vault = TokenVault(vault_dir=tmp_path)
        vault.store("delta",   {"x": 1})
        vault.store("binance", {"x": 2})
        exchanges = vault.list_exchanges()
        assert "delta"   in exchanges
        assert "binance" in exchanges

    def test_exists(self, tmp_path):
        from alchemy.tokens.vault import TokenVault
        vault = TokenVault(vault_dir=tmp_path)
        assert vault.exists("delta") is False
        vault.store("delta", {})
        assert vault.exists("delta") is True


# ── Token Models ──────────────────────────────────────────────────────────────
class TestTokenModels:
    def test_kite_token_not_expired(self):
        from alchemy.tokens.models import KiteToken
        from datetime import timezone
        t = KiteToken(api_key="k", api_secret="s",
                      access_token="tok",
                      expires_at=datetime.now(timezone.utc) + timedelta(hours=6))
        assert not t.is_expired
        assert t.is_authenticated

    def test_kite_token_expired(self):
        from alchemy.tokens.models import KiteToken
        t = KiteToken(api_key="k", api_secret="s",
                      expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        assert t.is_expired

    def test_token_needs_refresh_when_close_to_expiry(self):
        from alchemy.tokens.models import DeltaToken
        t = DeltaToken(api_key="k", api_secret="s",
                       expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
        assert t.needs_refresh

    def test_token_does_not_need_refresh_when_fresh(self):
        from alchemy.tokens.models import DeltaToken
        t = DeltaToken(api_key="k", api_secret="s",
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=48))
        assert not t.needs_refresh

    def test_to_safe_dict_redacts_key(self):
        from alchemy.tokens.models import BinanceToken
        t = BinanceToken(api_key="abcdefghijklmnop", api_secret="secret")
        d = t.to_safe_dict()
        assert "secret" not in str(d)
        assert "abcdef" in d["api_key"]   # Prefix visible

    def test_mark_used_increments_count(self):
        from alchemy.tokens.models import DeltaToken
        t = DeltaToken(api_key="k", api_secret="s")
        t.mark_used(); t.mark_used()
        assert t.use_count == 2

    def test_ib_token_never_expires(self):
        from alchemy.tokens.models import IBToken
        t = IBToken(api_key="k", api_secret="s")
        assert not t.is_expired


# ── TokenManager ─────────────────────────────────────────────────────────────
class TestTokenManager:
    def _make(self, tmp_path):
        from alchemy.tokens.manager import TokenManager
        from alchemy.tokens.vault import TokenVault
        vault = TokenVault(vault_dir=tmp_path)
        return TokenManager(vault=vault)

    def test_register_and_get(self, tmp_path):
        from alchemy.tokens.models import DeltaToken, ExchangeID
        mgr = self._make(tmp_path)
        tok = DeltaToken(api_key="key123", api_secret="sec", paper_mode=True)
        mgr.register(tok)
        retrieved = mgr.get_token(ExchangeID.DELTA)
        assert retrieved.api_key == "key123"
        assert retrieved.paper_mode is True

    def test_get_missing_raises(self, tmp_path):
        from alchemy.tokens.manager import TokenError
        from alchemy.tokens.models import ExchangeID
        mgr = self._make(tmp_path)
        with pytest.raises(TokenError, match="No token registered"):
            mgr.get_token(ExchangeID.BINANCE)

    def test_deregister(self, tmp_path):
        from alchemy.tokens.models import BinanceToken, ExchangeID
        mgr = self._make(tmp_path)
        mgr.register(BinanceToken(api_key="k", api_secret="s"))
        mgr.deregister(ExchangeID.BINANCE)
        assert mgr.get_token_safe(ExchangeID.BINANCE) is None

    def test_status_shows_all_exchanges(self, tmp_path):
        mgr = self._make(tmp_path)
        status = mgr.status()
        assert "kite"    in status
        assert "delta"   in status
        assert "binance" in status
        assert "ib"      in status

    def test_paper_mode_validate_always_true(self, tmp_path):
        from alchemy.tokens.models import DeltaToken, ExchangeID
        mgr = self._make(tmp_path)
        mgr.register(DeltaToken(api_key="k", api_secret="s", paper_mode=True))
        result = mgr.validate_token(ExchangeID.DELTA)
        assert result is True

    def test_update_kite_access_token(self, tmp_path):
        from alchemy.tokens.models import KiteToken, ExchangeID
        mgr = self._make(tmp_path)
        mgr.register(KiteToken(api_key="k", api_secret="s"))
        mgr.update_kite_access_token("new_daily_token")
        tok = mgr.get_token(ExchangeID.KITE)
        assert tok.access_token == "new_daily_token"
        assert tok.expires_at is not None


# ── WorkflowStates ────────────────────────────────────────────────────────────
class TestWorkflowStates:
    def _make_state(self):
        from alchemy.workflows.states import OrderWorkflowState, OrderRequest, OrderSide, OrderType
        return OrderWorkflowState(
            workflow_id="WF-TEST-001",
            request=OrderRequest(
                symbol="BTCUSD", exchange="delta",
                side=OrderSide.BUY, quantity=1.0,
                order_type=OrderType.MARKET, leverage=5
            )
        )

    def test_initial_status_pending(self):
        ws = self._make_state()
        from alchemy.workflows.states import WorkflowStatus
        assert ws.status == WorkflowStatus.PENDING

    def test_valid_transition(self):
        from alchemy.workflows.states import WorkflowStatus
        ws = self._make_state()
        ws.transition(WorkflowStatus.SIGNAL_VALIDATED, "OK")
        assert ws.status == WorkflowStatus.SIGNAL_VALIDATED
        assert len(ws.steps) == 1

    def test_invalid_transition_raises(self):
        from alchemy.workflows.states import WorkflowStatus
        ws = self._make_state()
        with pytest.raises(ValueError, match="Invalid transition"):
            ws.transition(WorkflowStatus.FILLED)   # Can't jump from PENDING to FILLED

    def test_is_terminal_on_settled(self):
        from alchemy.workflows.states import WorkflowStatus
        ws = self._make_state()
        ws.status = WorkflowStatus.SETTLED
        assert ws.is_terminal

    def test_add_error_appends(self):
        ws = self._make_state()
        ws.add_error("test error"); ws.add_error("another")
        assert len(ws.errors) == 2
        assert "test error" in ws.errors[0]

    def test_to_summary_has_required_keys(self):
        ws = self._make_state()
        s = ws.to_summary()
        for key in ["workflow_id","symbol","exchange","side","status","steps"]:
            assert key in s


# ── Validate Signal Node ──────────────────────────────────────────────────────
class TestValidateSignalNode:
    def _run(self, symbol="BTCUSD", quantity=1.0, order_type="market", leverage=5):
        from alchemy.workflows.engine import validate_signal_node
        from alchemy.workflows.states import OrderWorkflowState, OrderRequest, OrderSide, OrderType
        ws = OrderWorkflowState(
            workflow_id="TEST",
            request=OrderRequest(symbol=symbol, exchange="delta",
                                  side=OrderSide.BUY, quantity=quantity,
                                  order_type=OrderType(order_type), leverage=leverage)
        )
        return OrderWorkflowState(**validate_signal_node(ws.model_dump(mode="json")))

    def test_valid_order_passes(self):
        from alchemy.workflows.states import WorkflowStatus
        result = self._run()
        assert result.status == WorkflowStatus.SIGNAL_VALIDATED
        assert result.signal_valid is True

    def test_empty_symbol_fails(self):
        from alchemy.workflows.states import WorkflowStatus
        result = self._run(symbol="")
        assert result.status == WorkflowStatus.ERROR
        assert result.signal_valid is False

    def test_zero_quantity_fails(self):
        result = self._run(quantity=0)
        assert result.signal_valid is False

    def test_excessive_leverage_fails(self):
        result = self._run(leverage=200)
        assert result.signal_valid is False
