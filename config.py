"""
Configuration management for the Alchemy crypto trading bot.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DeltaConfig:
    api_key: str = field(default_factory=lambda: os.getenv("DELTA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("DELTA_API_SECRET", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "DELTA_BASE_URL", "https://api.india.delta.exchange"
        )
    )
    ws_url: str = "wss://socket.india.delta.exchange"


@dataclass
class AnthropicConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = "claude-opus-4-6"


@dataclass
class NewsConfig:
    news_api_key: str = field(default_factory=lambda: os.getenv("NEWS_API_KEY", ""))
    geopolitical_keywords: List[str] = field(
        default_factory=lambda: [
            "war",
            "conflict",
            "sanctions",
            "inflation",
            "recession",
            "interest rate",
            "central bank",
            "federal reserve",
            "SEC",
            "regulation",
            "ban",
            "crypto",
            "bitcoin",
            "geopolitical",
            "nato",
            "china",
            "russia",
            "middle east",
            "oil",
            "energy crisis",
            "trade war",
            "tariff",
            "election",
            "coup",
            "nuclear",
            "ceasefire",
            "peace deal",
            "economic crisis",
            "debt ceiling",
            "banking crisis",
            "dollar",
            "yen",
            "euro",
            "currency",
            "IMF",
            "World Bank",
        ]
    )
    rss_feeds: List[str] = field(
        default_factory=lambda: [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "https://feeds.reuters.com/reuters/worldNews",
            "https://www.aljazeera.com/xml/rss/all.xml",
            "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
            "https://cryptopanic.com/news/rss/",
        ]
    )
    fetch_interval_minutes: int = 15
    max_articles_per_fetch: int = 50


@dataclass
class TradingConfig:
    symbol: str = field(default_factory=lambda: os.getenv("TRADING_SYMBOL", "BTCUSD"))
    position_size_usd: float = field(
        default_factory=lambda: float(os.getenv("POSITION_SIZE_USD", "100"))
    )
    max_open_positions: int = field(
        default_factory=lambda: int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    )
    risk_per_trade_pct: float = field(
        default_factory=lambda: float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    )
    bullish_threshold: float = field(
        default_factory=lambda: float(os.getenv("BULLISH_THRESHOLD", "0.6"))
    )
    bearish_threshold: float = field(
        default_factory=lambda: float(os.getenv("BEARISH_THRESHOLD", "-0.6"))
    )
    stop_loss_pct: float = 2.0
    # TP widened from 4.0 → 4.5 so net R:R stays ≥ 1.5 after round-trip brokerage
    take_profit_pct: float = 4.5
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "true").lower() == "true"
    )
    leverage: int = 5
    analysis_interval_minutes: int = 30
    # ── Brokerage fees (Delta Exchange India) ──────────────────────────────────
    # Market orders (taker): 0.05 % per side → 0.10 % round-trip on notional.
    # At 5× leverage the effective cost on margin ≈ 0.50 % per trade.
    taker_fee_rate: float = field(
        default_factory=lambda: float(os.getenv("TAKER_FEE_RATE", "0.0005"))
    )
    maker_fee_rate: float = field(
        default_factory=lambda: float(os.getenv("MAKER_FEE_RATE", "0.0002"))
    )
    # ── Multi-contract scanning ────────────────────────────────────────────────
    watch_list: List[str] = field(
        default_factory=lambda: [
            s.strip()
            for s in os.getenv(
                "WATCH_LIST",
                "BTCUSD,ETHUSD,SOLUSD,BNBUSD,XRPUSD,AVAXUSD,DOGEUSD,MATICUSD,LINKUSD,DOTUSD",
            ).split(",")
            if s.strip()
        ]
    )
    top_contracts_to_trade: int = field(
        default_factory=lambda: int(os.getenv("TOP_CONTRACTS_TO_TRADE", "3"))
    )
    scan_all_contracts: bool = field(
        default_factory=lambda: (
            os.getenv("SCAN_ALL_CONTRACTS", "false").lower() == "true"
        )
    )


@dataclass
class AuthConfig:
    """Authentication + 2FA configuration.

    Generate initial credentials with:
        python scripts/setup_auth.py
    """

    enabled: bool = field(
        default_factory=lambda: os.getenv("AUTH_ENABLED", "true").lower() == "true"
    )
    username: str = field(default_factory=lambda: os.getenv("AUTH_USERNAME", "admin"))
    # bcrypt hash of the admin password — generate with scripts/setup_auth.py
    password_hash: str = field(
        default_factory=lambda: os.getenv("AUTH_PASSWORD_HASH", "")
    )
    # 64-char hex key used to sign JWTs — generate with scripts/setup_auth.py
    jwt_secret_key: str = field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", ""))
    # base32 TOTP secret — generate with scripts/setup_auth.py, then scan QR code
    totp_secret: str = field(default_factory=lambda: os.getenv("TOTP_SECRET", ""))


@dataclass
class AppConfig:
    delta: DeltaConfig = field(default_factory=DeltaConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    def validate(self):
        errors = []
        if not self.anthropic.api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        if not self.delta.api_key and not self.trading.dry_run:
            errors.append("DELTA_API_KEY is required for live trading")
        if not self.delta.api_secret and not self.trading.dry_run:
            errors.append("DELTA_API_SECRET is required for live trading")
        if errors:
            raise ValueError(
                "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            )
        return True


# Global config instance
config = AppConfig()
