"""Application settings, loaded from environment / .env."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
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
    fmp_api_key: str = Field(
        ...,
        description="Financial Modeling Prep API key. Required for global fundamentals (M2).",
    )
    ibkr_host: str = Field(
        default="127.0.0.1",
        description="Host of the running TWS / IB Gateway socket (M5).",
    )
    ibkr_port: int = Field(
        default=7496,
        description=(
            "TWS API socket port. 7496 = live TWS (default), 7497 = paper TWS, "
            "4001/4002 = IB Gateway live/paper."
        ),
    )
    ibkr_client_id: int = Field(
        default=1,
        description="Client id for the TWS API connection. Each concurrent client needs a distinct id.",
    )
    reports_dir: Path = Field(default=Path("./reports"))
    presets_dir: Path = Field(
        default=Path("./config/presets"),
        description="Directory holding screener preset YAMLs (resolved by `bot screen --preset`).",
    )
    industry_mapping_path: Path | None = Field(
        default=None,
        description=(
            "Optional CSV mapping provider industry labels to the Damodaran taxonomy "
            "(spec §4.3.1). Unset uses the mapping shipped with the package."
        ),
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")

    @field_validator("industry_mapping_path", mode="before")
    @classmethod
    def _blank_path_is_unset(cls, value: object) -> object:
        """Treat ``BOT_INDUSTRY_MAPPING_PATH=`` as "not configured".

        Without this, an empty or whitespace env var coerces to ``Path(".")``,
        which exists, so path resolution hands the CSV loader a *directory*.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


def load_settings() -> Settings:
    """Load settings; raises on missing required fields."""
    return Settings()  # type: ignore[call-arg]  # values supplied via env vars
