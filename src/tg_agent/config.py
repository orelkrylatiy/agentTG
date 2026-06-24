"""
Application configuration using pydantic-settings.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["dev", "prod", "test"] = Field(default="dev", alias="APP_ENV")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )

    # Telegram API
    tg_api_id: int = Field(..., alias="TG_API_ID")
    tg_api_hash: str = Field(..., alias="TG_API_HASH")
    tg_phone: str = Field(..., alias="TG_PHONE")

    # Telethon session
    telethon_session_name: str = Field(
        default="data/userbot.session", alias="TELETHON_SESSION_NAME"
    )

    # Control bot
    control_bot_token: str = Field(..., alias="CONTROL_BOT_TOKEN")
    owner_telegram_id: int = Field(..., alias="OWNER_TELEGRAM_ID")

    # Database
    database_url: str = Field(
        default="sqlite:///./data/agent.db", alias="DATABASE_URL"
    )

    # Agent state
    agent_global_enabled: bool = Field(default=False, alias="AGENT_GLOBAL_ENABLED")
    default_chat_mode: Literal["OFF", "WATCH", "DRAFT", "AUTO"] = Field(
        default="DRAFT", alias="DEFAULT_CHAT_MODE"
    )

    # LLM configuration
    llm_provider: Literal["chatgpt_oauth", "openai", "openrouter"] = Field(
        default="chatgpt_oauth", alias="LLM_PROVIDER"
    )
    llm_model: str = Field(default="chatgpt/gpt-5", alias="LLM_MODEL")
    litellm_chatgpt_enabled: bool = Field(default=True, alias="LITELLM_CHATGPT_ENABLED")

    # Fallback providers
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_fallback_model: str = Field(default="gpt-4o-mini", alias="OPENAI_FALLBACK_MODEL")

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_fallback_model: str = Field(
        default="openrouter/openai/gpt-4o-mini", alias="OPENROUTER_FALLBACK_MODEL"
    )

    # Rate limiting
    cooldown_seconds: int = Field(default=120, alias="COOLDOWN_SECONDS")

    # Owner takeover
    owner_takeover_pause_minutes: int = Field(
        default=30, alias="OWNER_TAKEOVER_PAUSE_MINUTES"
    )

    # Context limits
    max_context_messages: int = Field(default=12, alias="MAX_CONTEXT_MESSAGES")
    max_reply_chars: int = Field(default=800, alias="MAX_REPLY_CHARS")

    # Safety settings
    require_approval_for_unknown_chats: bool = Field(
        default=True, alias="REQUIRE_APPROVAL_FOR_UNKNOWN_CHATS"
    )
    require_approval_for_initiative_messages: bool = Field(
        default=True, alias="REQUIRE_APPROVAL_FOR_INITIATIVE_MESSAGES"
    )
    require_approval_for_money_or_commitments: bool = Field(
        default=True, alias="REQUIRE_APPROVAL_FOR_MONEY_OR_COMMITMENTS"
    )

    @field_validator("tg_api_id")
    @classmethod
    def validate_api_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("TG_API_ID must be a positive integer")
        return v

    @field_validator("tg_api_hash")
    @classmethod
    def validate_api_hash(cls, v: str) -> str:
        if not v or v == "replace_me":
            raise ValueError("TG_API_HASH must be set")
        return v

    @field_validator("control_bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or v == "replace_me":
            raise ValueError("CONTROL_BOT_TOKEN must be set")
        return v

    @property
    def project_root(self) -> Path:
        """Return project root directory."""
        return Path(__file__).parent.parent.parent

    @property
    def prompts_dir(self) -> Path:
        """Return prompts directory."""
        return self.project_root / "prompts"

    @property
    def data_dir(self) -> Path:
        """Return data directory for session and database."""
        data_path = Path(self.telethon_session_name).parent
        if data_path.is_absolute():
            return data_path
        return self.project_root / data_path


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
