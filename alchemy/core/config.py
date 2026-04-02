"""
alchemy.core.config
===================
Centralised configuration using pydantic-settings.
Loads from environment variables and config/settings.yaml.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LiteLLM / provider configuration."""
    model_config = SettingsConfigDict(env_prefix="LLM_")

    primary_model: str = "claude-sonnet-4-6"
    fallback_model: str = "gpt-4o"
    gateway_url: str = "http://localhost:4000"
    gateway_port: int = 4000
    max_budget_usd: float = 50.0
    anthropic_api_key: Optional[SecretStr] = Field(None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[SecretStr] = Field(None, alias="OPENAI_API_KEY")
    google_api_key: Optional[SecretStr] = Field(None, alias="GOOGLE_API_KEY")
    litellm_master_key: Optional[SecretStr] = Field(None, alias="LITELLM_MASTER_KEY")
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout_seconds: int = 30


class IBConfig(BaseSettings):
    """Interactive Brokers connection configuration."""
    model_config = SettingsConfigDict(env_prefix="IB_")

    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    account: Optional[str] = None
    paper_trading: bool = True
    reconnect_interval_s: int = 5
    max_reconnect_attempts: int = 10


class KiteConfig(BaseSettings):
    """Zerodha Kite Connect configuration."""
    model_config = SettingsConfigDict(env_prefix="KITE_")

    api_key: Optional[SecretStr] = None
    api_secret: Optional[SecretStr] = None
    access_token: Optional[SecretStr] = None
    paper_trading: bool = True


class DatabaseConfig(BaseSettings):
    """TimescaleDB / Redis configuration."""
    model_config = SettingsConfigDict(env_prefix="DB_")

    timescale_url: str = "postgresql://alchemy:alchemy@localhost:5432/alchemy"
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 1800
    pool_size: int = 10


class RiskConfig(BaseSettings):
    """Risk management parameters."""
    model_config = SettingsConfigDict(env_prefix="RISK_")

    max_position_pct: float = Field(0.05, ge=0.001, le=0.50)
    max_portfolio_drawdown_pct: float = Field(0.10, ge=0.01, le=0.50)
    max_daily_loss_usd: float = 5000.0
    max_open_positions: int = 20
    default_stop_loss_pct: float = 0.02
    default_take_profit_pct: float = 0.04
    vol_scaling: bool = True
    max_vol_threshold: float = 0.40

    @field_validator("max_position_pct")
    @classmethod
    def validate_position(cls, v: float) -> float:
        if v > 0.20:
            raise ValueError("max_position_pct > 20% is not recommended for diversification")
        return v


class AlchemyConfig(BaseSettings):
    """Root configuration object for the Alchemy platform."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Meta
    env: Literal["development", "paper", "production"] = "paper"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    project_name: str = "alchemy"

    # Sub-configs (loaded from environment prefix)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    ib: IBConfig = Field(default_factory=IBConfig)
    kite: KiteConfig = Field(default_factory=KiteConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    # Feature flags
    enable_ai_agents: bool = True
    enable_ib_execution: bool = False
    enable_kite_execution: bool = False
    enable_pyfolio_reports: bool = True
    enable_garch_volatility: bool = True


@lru_cache(maxsize=1)
def get_config() -> AlchemyConfig:
    """Return singleton config instance (cached)."""
    return AlchemyConfig()
