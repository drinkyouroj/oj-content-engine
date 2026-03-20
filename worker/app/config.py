"""
Application configuration via environment variables.

Reads from .env file or environment. Required vars fail fast on startup.
Implements PRD Section 8 (Tech Stack Decisions).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker application settings. Required vars have no default and will
    raise ValidationError if missing from the environment."""

    # Required — Worker cannot start without these
    database_url: str
    arq_redis_url: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str

    # Optional — not needed for scaffold, required by future feature branches
    anthropic_api_key: str = ""  # Legacy — kept for backward compat
    groq_api_key: str = ""
    notion_api_key: str = ""
    notion_db_id: str = ""
    worker_secret: str = ""

    # RSS/social sources — populated by feature/discovery
    rss_feed_urls: str = ""
    twitter_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    """Instantiate and return application settings.

    Returns:
        Settings loaded from environment variables.

    Raises:
        pydantic.ValidationError: If required env vars are missing.
    """
    return Settings()
