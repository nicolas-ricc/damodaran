"""Application settings, loaded from environment / .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the bot."""

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default=Path("./bot.duckdb"))
    sec_user_agent: str = Field(
        ...,
        description="User-Agent header for SEC EDGAR requests. Required by SEC fair-use policy.",
    )
    reports_dir: Path = Field(default=Path("./reports"))
    log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    """Load settings; raises on missing required fields."""
    return Settings()  # type: ignore[call-arg]
