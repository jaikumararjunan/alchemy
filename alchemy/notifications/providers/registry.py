"""
alchemy.notifications.providers.registry
==========================================
Provider registry — the plugin system.

Adding a new notification channel:
  1. Create alchemy/notifications/providers/{name}.py
  2. Implement BaseNotificationProvider
  3. Add one line here: registry.register(YourProvider())

The dispatcher auto-discovers all registered providers.

Example — adding Discord in 5 minutes:

    # 1. Create alchemy/notifications/providers/discord.py
    class DiscordProvider(BaseNotificationProvider):
        provider_type = ProviderType.DISCORD
        display_name = "Discord"
        config_fields = [ConfigField("webhook_url", "Webhook URL", required=True)]

        async def send(self, channel, event):
            import httpx
            text = self.format_message(event, "plain")
            r = await httpx.AsyncClient().post(
                channel.config["webhook_url"],
                json={"content": text, "username": "Alchemy"}
            )
            return SendResult(success=r.status_code < 400, provider="discord")

        def validate_config(self, config):
            self._check_required(config, "webhook_url")

    # 2. Register here (3 lines below)
    from alchemy.notifications.providers.discord import DiscordProvider
    registry.register(DiscordProvider())
    # Done. The UI and API will immediately show Discord as an option.
"""
from __future__ import annotations

from typing import Optional

import structlog

from alchemy.notifications.base import BaseNotificationProvider
from alchemy.notifications.models import ProviderType

log = structlog.get_logger(__name__)


class ProviderRegistry:
    """
    Central registry of all available notification providers.
    Thread-safe singleton.
    """

    def __init__(self) -> None:
        self._providers: dict[ProviderType, BaseNotificationProvider] = {}

    def register(self, provider: BaseNotificationProvider) -> None:
        """Register a provider. Overwrites if same type already registered."""
        pt = provider.provider_type
        self._providers[pt] = provider
        log.info("notification.provider_registered",
                 provider=pt.value, name=provider.display_name)

    def get(self, provider_type: ProviderType) -> Optional[BaseNotificationProvider]:
        return self._providers.get(provider_type)

    def get_or_raise(self, provider_type: ProviderType) -> BaseNotificationProvider:
        p = self._providers.get(provider_type)
        if not p:
            raise ValueError(
                f"No provider registered for '{provider_type.value}'. "
                f"Available: {self.available_types()}"
            )
        return p

    def all_providers(self) -> list[BaseNotificationProvider]:
        return list(self._providers.values())

    def available_types(self) -> list[str]:
        return [pt.value for pt in self._providers]

    def provider_metadata(self) -> list[dict]:
        """Return UI-friendly metadata for all registered providers."""
        return [
            {
                "type":         p.provider_type.value,
                "name":         p.display_name,
                "icon":         p.emoji_icon,
                "config_fields":[
                    {
                        "key":        f.key,
                        "label":      f.label,
                        "placeholder":f.placeholder,
                        "required":   f.required,
                        "secret":     f.secret,
                        "help_text":  f.help_text,
                        "field_type": f.field_type,
                    }
                    for f in p.config_fields
                ],
                "setup_instructions": p.get_setup_instructions(),
            }
            for p in self._providers.values()
        ]

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, pt: ProviderType) -> bool:
        return pt in self._providers


# ── Singleton registry + auto-registration ────────────────────────────────────

registry = ProviderRegistry()


def _bootstrap_providers() -> None:
    """
    Register all built-in providers.
    Import errors are caught individually so one broken provider
    doesn't prevent others from loading.
    """
    providers_to_load = [
        ("alchemy.notifications.providers.telegram",       "TelegramProvider"),
        ("alchemy.notifications.providers.whatsapp",       "WhatsAppProvider"),
        ("alchemy.notifications.providers.sms",            "SMSProvider"),
        ("alchemy.notifications.providers.email_provider", "EmailProvider"),
        # ── Add new providers here ──────────────────────────────────────────
        # ("alchemy.notifications.providers.slack",   "SlackProvider"),
        # ("alchemy.notifications.providers.discord", "DiscordProvider"),
        # ("alchemy.notifications.providers.webhook", "WebhookProvider"),
        # ("alchemy.notifications.providers.pushover","PushoverProvider"),
    ]

    for module_path, class_name in providers_to_load:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            registry.register(cls())
        except ImportError as e:
            log.warning("notification.provider_import_skip",
                        module=module_path, error=str(e))
        except Exception as e:
            log.error("notification.provider_load_error",
                      module=module_path, error=str(e))

    log.info("notification.registry_ready",
             providers=registry.available_types(),
             count=len(registry))


# Auto-bootstrap on import
_bootstrap_providers()
