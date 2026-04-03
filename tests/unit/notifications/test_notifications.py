"""tests/unit/notifications/test_notifications.py"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


# ── Provider Registry ─────────────────────────────────────────────────────────
class TestProviderRegistry:
    def test_registry_has_three_providers(self):
        from alchemy.notifications.providers.registry import registry
        types = registry.available_types()
        assert "telegram"  in types
        assert "whatsapp"  in types
        assert "sms"       in types
        assert len(types) >= 3

    def test_get_existing_provider(self):
        from alchemy.notifications.providers.registry import registry
        from alchemy.notifications.models import ProviderType
        p = registry.get(ProviderType.TELEGRAM)
        assert p is not None
        assert p.display_name == "Telegram"

    def test_get_missing_returns_none(self):
        from alchemy.notifications.providers.registry import registry
        from alchemy.notifications.models import ProviderType
        p = registry.get(ProviderType.EMAIL)  # not registered
        assert p is None

    def test_get_or_raise_missing(self):
        from alchemy.notifications.providers.registry import registry
        from alchemy.notifications.models import ProviderType
        with pytest.raises(ValueError, match="No provider"):
            registry.get_or_raise(ProviderType.EMAIL)

    def test_provider_metadata_has_config_fields(self):
        from alchemy.notifications.providers.registry import registry
        meta = registry.provider_metadata()
        assert len(meta) >= 3
        for m in meta:
            assert "type" in m
            assert "name" in m
            assert "config_fields" in m
            assert "setup_instructions" in m

    def test_register_custom_provider(self):
        from alchemy.notifications.providers.registry import ProviderRegistry
        from alchemy.notifications.base import BaseNotificationProvider, ConfigField, SendResult
        from alchemy.notifications.models import ProviderType, NotificationChannel, NotificationEvent

        class TestProvider(BaseNotificationProvider):
            provider_type = ProviderType.WEBHOOK
            display_name  = "Test Webhook"
            config_fields = [ConfigField("url","URL",required=True)]
            async def send(self, ch, ev): return SendResult(success=True, provider="webhook")
            def validate_config(self, cfg): self._check_required(cfg,"url")

        reg = ProviderRegistry()
        reg.register(TestProvider())
        assert ProviderType.WEBHOOK in reg
        assert reg.get(ProviderType.WEBHOOK).display_name == "Test Webhook"


# ── Base Provider ─────────────────────────────────────────────────────────────
class TestBaseProvider:
    def _make_event(self, severity="info", title="Test Alert", message="Test message"):
        from alchemy.notifications.models import (
            NotificationEvent, EventType, EventSeverity
        )
        return NotificationEvent(
            event_type=EventType.CUSTOM,
            severity=EventSeverity(severity),
            title=title,
            message=message,
            source="test",
        )

    def test_format_message_plain(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        p  = TelegramProvider()
        ev = self._make_event("info", "BUY Signal", "RELIANCE at 2850")
        text = p.format_message(ev, "plain")
        assert "BUY Signal" in text
        assert "RELIANCE" in text

    def test_format_message_truncated_for_sms(self):
        from alchemy.notifications.providers.sms import SMSProvider
        from alchemy.notifications.models import NotificationEvent, EventType, EventSeverity
        p  = SMSProvider()
        ev = NotificationEvent(
            event_type=EventType.CUSTOM, severity=EventSeverity.INFO,
            title="Alert", message="x" * 200, source="test"
        )
        text = p.format_message(ev, "plain")
        assert len(text) <= 160

    def test_severity_emoji_included(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        from alchemy.notifications.models import EventSeverity
        p  = TelegramProvider()
        ev = self._make_event("critical", "Emergency Stop", "All trading halted")
        text = p.format_message(ev, "plain")
        assert "🚨" in text

    def test_required_fields_list(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        p = TelegramProvider()
        req = p.required_fields()
        assert "bot_token" in req
        assert "chat_id" in req


# ── Telegram Provider ─────────────────────────────────────────────────────────
class TestTelegramProvider:
    def test_validate_valid_config(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        p = TelegramProvider()
        p.validate_config({"bot_token": "5432198765:AAFr8kXYabcdef1234567890abcdef1234567", "chat_id": "123456"})

    def test_validate_missing_bot_token(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        with pytest.raises(ValueError, match="bot_token"):
            TelegramProvider().validate_config({"chat_id": "123"})

    def test_validate_short_token(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        with pytest.raises(ValueError, match="invalid"):
            TelegramProvider().validate_config({"bot_token": "shorttoken", "chat_id": "123"})

    @pytest.mark.asyncio
    async def test_send_success(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        from alchemy.notifications.models import (
            NotificationChannel, NotificationEvent, EventType,
            EventSeverity, ProviderType
        )
        p = TelegramProvider()
        channel = NotificationChannel(
            user_id="test", provider=ProviderType.TELEGRAM, name="Test",
            config={"bot_token": "5432198765:AAFr8kXYtest", "chat_id": "123456"}
        )
        event = NotificationEvent(
            event_type=EventType.SIGNAL_BUY, severity=EventSeverity.INFO,
            title="BUY BTCUSD", message="AI signal generated", source="test"
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            result = await p.send(channel, event)

        assert result.success is True
        assert result.message_id == "42"

    @pytest.mark.asyncio
    async def test_send_failure(self):
        from alchemy.notifications.providers.telegram import TelegramProvider
        from alchemy.notifications.models import (
            NotificationChannel, NotificationEvent, EventType,
            EventSeverity, ProviderType
        )
        p = TelegramProvider()
        channel = NotificationChannel(
            user_id="test", provider=ProviderType.TELEGRAM, name="Test",
            config={"bot_token": "bad_token", "chat_id": "123"}
        )
        event = NotificationEvent(event_type=EventType.CUSTOM, severity=EventSeverity.INFO,
                                   title="t", message="m", source="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"ok": False, "description": "Unauthorized"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            result = await p.send(channel, event)

        assert result.success is False
        assert "Unauthorized" in result.error


# ── SMS Provider ──────────────────────────────────────────────────────────────
class TestSMSProvider:
    def test_validate_twilio_config(self):
        from alchemy.notifications.providers.sms import SMSProvider
        p = SMSProvider()
        p.validate_config({
            "backend": "twilio", "to_number": "+919876543210",
            "account_sid": "ACtest123", "auth_token": "token123", "from_number": "+12015551234"
        })

    def test_validate_msg91_config(self):
        from alchemy.notifications.providers.sms import SMSProvider
        p = SMSProvider()
        p.validate_config({
            "backend": "msg91", "to_number": "+919876543210",
            "api_key": "testkey", "sender_id": "ALCHMY"
        })

    def test_validate_missing_backend(self):
        from alchemy.notifications.providers.sms import SMSProvider
        with pytest.raises(ValueError):
            SMSProvider().validate_config({"to_number": "+919876543210"})

    def test_normalise_10digit_indian_number(self):
        from alchemy.notifications.providers.sms import SMSProvider
        p = SMSProvider()
        assert p._normalise_number("9876543210") == "+919876543210"
        assert p._normalise_number("+919876543210") == "+919876543210"

    def test_validate_unknown_backend(self):
        from alchemy.notifications.providers.sms import SMSProvider
        with pytest.raises(ValueError, match="Unknown SMS backend"):
            SMSProvider().validate_config({
                "backend": "pigeons", "to_number": "+919876543210"
            })


# ── WhatsApp Provider ─────────────────────────────────────────────────────────
class TestWhatsAppProvider:
    def test_validate_twilio_config(self):
        from alchemy.notifications.providers.whatsapp import WhatsAppProvider
        p = WhatsAppProvider()
        p.validate_config({
            "backend": "twilio", "to_number": "+919876543210",
            "account_sid": "ACtest", "auth_token": "token",
            "from_number": "whatsapp:+14155238886"
        })

    def test_validate_meta_config(self):
        from alchemy.notifications.providers.whatsapp import WhatsAppProvider
        p = WhatsAppProvider()
        p.validate_config({
            "backend": "meta", "to_number": "+919876543210",
            "access_token": "token", "phone_number_id": "12345678"
        })

    def test_validate_no_plus_prefix_fails(self):
        from alchemy.notifications.providers.whatsapp import WhatsAppProvider
        with pytest.raises(ValueError, match="E.164"):
            WhatsAppProvider().validate_config({
                "backend": "twilio", "to_number": "9876543210",
                "account_sid": "AC", "auth_token": "tok", "from_number": "wa:+"
            })


# ── Dispatcher ────────────────────────────────────────────────────────────────
class TestDispatcher:
    def _make_event(self):
        from alchemy.notifications.models import (
            NotificationEvent, EventType, EventSeverity
        )
        return NotificationEvent(
            event_type=EventType.ORDER_FILLED,
            severity=EventSeverity.SUCCESS,
            user_id="user-1",
            title="Order Filled",
            message="BTCUSD filled at 68400",
            source="test",
        )

    def test_add_and_get_channel(self):
        from alchemy.notifications.dispatcher import NotificationDispatcher
        from alchemy.notifications.models import NotificationChannel, ProviderType
        d = NotificationDispatcher()
        ch = NotificationChannel(user_id="u1", provider=ProviderType.TELEGRAM,
                                  name="T", config={"bot_token":"t","chat_id":"1"})
        d.add_channel(ch)
        channels = d.get_channels("u1")
        assert len(channels) == 1
        assert channels[0].id == ch.id

    def test_remove_channel(self):
        from alchemy.notifications.dispatcher import NotificationDispatcher
        from alchemy.notifications.models import NotificationChannel, ProviderType
        d = NotificationDispatcher()
        ch = NotificationChannel(user_id="u2", provider=ProviderType.SMS,
                                  name="SMS", config={"backend":"twilio","to_number":"+91123"})
        d.add_channel(ch)
        removed = d.remove_channel("u2", ch.id)
        assert removed is True
        assert d.get_channels("u2") == []

    def test_rate_limit_blocks_after_max(self):
        from alchemy.notifications.dispatcher import NotificationDispatcher
        d = NotificationDispatcher()
        for _ in range(50):
            result = d._check_user_rate_limit("heavy-user", max_per_hour=50)
        # 51st should be blocked
        blocked = d._check_user_rate_limit("heavy-user", max_per_hour=50)
        assert blocked is False

    def test_deduplication_by_idempotency_key(self):
        from alchemy.notifications.dispatcher import NotificationDispatcher
        from alchemy.notifications.models import NotificationEvent, EventType, EventSeverity
        d = NotificationDispatcher()
        ev = NotificationEvent(
            event_type=EventType.CUSTOM, severity=EventSeverity.INFO,
            title="t", message="m", source="test",
            idempotency_key="order-WF-123-filled",
        )
        # First send — not duplicate
        assert ev.idempotency_key not in d._sent_ids
        d._sent_ids.add(ev.idempotency_key)
        # Second send — should be caught
        assert ev.idempotency_key in d._sent_ids


# ── NotificationEvent factories ───────────────────────────────────────────────
class TestEventFactories:
    def test_from_signal_buy(self):
        from alchemy.notifications.models import NotificationEvent, EventType, EventSeverity
        from alchemy.core.state import TradingSignal

        class FakeSignal:
            signal = "BUY"; ticker = "RELIANCE"; market = "NSE"
            position_pct = 0.03; stop_loss_pct = 0.02; take_profit_pct = 0.04
            sentiment_score = 0.75; forecast_vol = 0.25; run_id = "test-1"

        ev = NotificationEvent.from_signal(FakeSignal(), user_id="u1")
        assert ev.event_type == EventType.SIGNAL_BUY
        assert "RELIANCE" in ev.title
        assert ev.user_id == "u1"
        assert "🟢" in ev.title

    def test_risk_alert_is_critical(self):
        from alchemy.notifications.models import NotificationEvent, EventSeverity, EventType
        ev = NotificationEvent.risk_alert({"daily_pnl": -5000, "current_drawdown": 0.08}, "u1")
        assert ev.severity == EventSeverity.CRITICAL
        assert ev.event_type == EventType.RISK_EMERGENCY_STOP
        assert "🚨" in ev.title
