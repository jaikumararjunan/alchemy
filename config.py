"""Configuration for Emotion Engine v2."""
import os
from dataclasses import dataclass, field


@dataclass
class ClaudeConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-4-6"))
    max_tokens: int = 2048
    temperature: float = 0.3


@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8001")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")


@dataclass
class StorageConfig:
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "storage/emotion_engine.db"))


@dataclass
class AppConfig:
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    def validate(self) -> None:
        if not self.claude.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        valid_models = [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ]
        if self.claude.model not in valid_models:
            raise ValueError(f"CLAUDE_MODEL must be one of {valid_models}")
