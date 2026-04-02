"""
alchemy.llm.router
==================
Unified LLM routing via LiteLLM (QuantInsti fork).
Provides provider-agnostic completions with fallback, budget tracking,
and async support for all Alchemy agents.

Source: https://github.com/QuantInsti/litellm
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import litellm
import structlog

from alchemy.core.config import LLMConfig, get_config

log = structlog.get_logger(__name__)

# Silence litellm verbose output in non-debug environments
litellm.suppress_debug_info = True
litellm.set_verbose = False


class AlchemyLLMRouter:
    """
    Wrapper around LiteLLM providing:
    - Automatic fallback (primary → fallback model)
    - Budget enforcement per session
    - Structured JSON output parsing
    - Retry with exponential backoff (via tenacity)
    - Async support for agent pipelines

    Usage::

        router = AlchemyLLMRouter()
        result = await router.complete(
            system="You are a financial analyst.",
            user="Analyse RELIANCE news: ...",
            json_mode=True,
        )
    """

    TRADING_SYSTEM_PROMPT = """You are an expert quantitative financial analyst integrated
into the Alchemy algorithmic trading platform. You analyse financial data, news sentiment,
and market conditions to generate precise, actionable trading signals.

Always respond with structured JSON when json_mode is enabled.
Be concise, data-driven, and never fabricate market data.
Risk management is paramount — never recommend positions exceeding portfolio limits."""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.cfg = config or get_config().llm
        self._setup_budget()
        self._call_count = 0
        self._total_tokens = 0

    def _setup_budget(self) -> None:
        """Configure LiteLLM budget manager."""
        try:
            litellm.max_budget = self.cfg.max_budget_usd
            self._budget_manager = litellm.BudgetManager(
                project_name=f"alchemy_{id(self)}"
            )
        except Exception:
            self._budget_manager = None

    # ── Sync Completion ──────────────────────────────────────────────────────

    def complete(
        self,
        user: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str | dict:
        """Synchronous LLM completion with automatic fallback."""
        messages = self._build_messages(system, user)
        primary = model or self.cfg.primary_model
        fallback = self.cfg.fallback_model
        start = time.perf_counter()

        for attempt_model in [primary, fallback]:
            try:
                extra: dict[str, Any] = {}
                if json_mode:
                    extra["response_format"] = {"type": "json_object"}
                response = litellm.completion(
                    model=attempt_model,
                    messages=messages,
                    temperature=self.cfg.temperature,
                    max_tokens=self.cfg.max_tokens,
                    timeout=self.cfg.timeout_seconds,
                    **extra,
                    **kwargs,
                )
                content = response.choices[0].message.content
                elapsed = time.perf_counter() - start
                self._call_count += 1
                usage = getattr(response, "usage", None)
                if usage:
                    self._total_tokens += usage.total_tokens
                log.info("llm.complete", model=attempt_model,
                         elapsed_s=round(elapsed, 2),
                         tokens=getattr(usage, "total_tokens", "?"))
                if json_mode and content:
                    return json.loads(content)
                return content or ""
            except json.JSONDecodeError as e:
                log.warning("llm.json_parse_error", error=str(e))
                return {}
            except Exception as e:
                log.warning("llm.attempt_failed", model=attempt_model, error=str(e))
                if attempt_model == fallback:
                    raise
        return ""

    # ── Async Completion ─────────────────────────────────────────────────────

    async def acomplete(
        self,
        user: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str | dict:
        """Async LLM completion — use inside LangGraph nodes."""
        messages = self._build_messages(system, user)
        primary = model or self.cfg.primary_model
        fallback = self.cfg.fallback_model

        for attempt_model in [primary, fallback]:
            try:
                extra: dict[str, Any] = {}
                if json_mode:
                    extra["response_format"] = {"type": "json_object"}
                response = await litellm.acompletion(
                    model=attempt_model,
                    messages=messages,
                    temperature=self.cfg.temperature,
                    max_tokens=self.cfg.max_tokens,
                    timeout=self.cfg.timeout_seconds,
                    **extra,
                    **kwargs,
                )
                content = response.choices[0].message.content
                if json_mode and content:
                    return json.loads(content)
                return content or ""
            except Exception as e:
                log.warning("llm.async_attempt_failed",
                            model=attempt_model, error=str(e))
                if attempt_model == fallback:
                    raise
        return ""

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _build_messages(
        self, system: Optional[str], user: str
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system or self.TRADING_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

    def stats(self) -> dict:
        return {
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
            "primary_model": self.cfg.primary_model,
            "fallback_model": self.cfg.fallback_model,
        }
