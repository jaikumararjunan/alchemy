"""
Alchemy Trading Platform
========================
AI-powered algorithmic trading platform integrating the QuantInsti ecosystem.

Modules:
    agents    — LangGraph multi-agent orchestration (AI-in-Trading-Workflow)
    analytics — Portfolio analytics + volatility (pyfolio + arch)
    data      — Market data adapters (quantrautil)
    execution — Broker gateways (ib-controller + kiteconnect)
    llm       — LLM router + gateway (litellm)
    pipeline  — Factor screening (zipline-pipeline)
    risk      — Risk management engine
    strategy  — Strategy factory + templates (blueshift-developer-kit)
    utils     — Shared utilities
"""

__version__ = "0.1.0"
__author__ = "Jai | Alchemy Platform"

from alchemy.core.state import AlchemyTradingState  # noqa: F401
from alchemy.core.config import AlchemyConfig  # noqa: F401

__all__ = ["AlchemyTradingState", "AlchemyConfig", "__version__"]
