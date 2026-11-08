"""Application settings, loaded from environment / .env."""

from datetime import date
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    data_provider: Literal["edgar-tiingo", "edgar-stooq", "fmp"] = Field(
        default="edgar-tiingo",
        description=(
            "Market data adapter (US-only, ADR 0007): 'edgar-tiingo' (SEC EDGAR fundamentals "
            "+ Tiingo EOD prices, needs a free BOT_TIINGO_API_KEY — recommended), 'edgar-stooq' "
            "(EDGAR + Stooq CSVs via BOT_STOOQ_DIR), or 'fmp' (needs BOT_FMP_API_KEY)."
        ),
    )
    fmp_api_key: str = Field(
        default="",
        description="Financial Modeling Prep API key. Required only when BOT_DATA_PROVIDER=fmp.",
    )
    tiingo_api_key: str = Field(
        default="",
        description=(
            "Tiingo API token (free at tiingo.com). Required only when "
            "BOT_DATA_PROVIDER=edgar-tiingo; supplies EOD prices for the universe."
        ),
    )
    stooq_dir: Path | None = Field(
        default=None,
        description=(
            "Directory of <TICKER>.csv files harvested by scripts/stooq_browser_fetch.mjs. "
            "When set (edgar-stooq provider only), refresh --prices reads these files instead "
            "of Stooq's HTTP endpoint, which is behind an anti-bot wall (ADR 0007)."
        ),
    )
    ibkr_flex_token: str = Field(
        default="",
        description=(
            "IBKR Flex Web Service token. Required by `bot portfolio`, which reads positions, "
            "cash, trades and corporate actions from one Activity Flex Query."
        ),
    )
    ibkr_flex_query_id: str = Field(
        default="",
        description=(
            "Id of the Activity Flex Query. Required by `bot portfolio`; sections: Open Positions, "
            "Cash Report, Trades, Corporate Actions, Cash Transactions."
        ),
    )
    ibkr_flex_tz: str = Field(
        default="America/New_York",
        description=(
            "IANA time zone of the Flex Query's trade dateTime values (the account's "
            "reporting time zone in Account Management)."
        ),
    )
    ibkr_flex_token_expires: date | None = Field(
        default=None,
        description=(
            "Expiry date (ISO, YYYY-MM-DD) of the Flex token. `bot doctor` warns from 14 days "
            "before it and fails once it has passed. Unset or blank: no check."
        ),
    )
    reports_dir: Path = Field(default=Path("./reports"))
    presets_dir: Path = Field(
        default=Path("./config/presets"),
        description="Directory holding screener preset YAMLs (resolved by `bot screen --preset`).",
    )
    currencies_path: Path = Field(
        default=Path("./config/currencies.yaml"),
        description="Curated per-currency risk-free rate and nominal GDP growth table (#109).",
    )
    default_spreads_path: Path = Field(
        default=Path("./config/default_spreads.yaml"),
        description="Curated interest coverage → synthetic rating → cumulative default probability tables for distressed stories (#213).",
    )
    assumptions_dir: Path = Field(
        default=Path("./config/assumptions"),
        description="Convention-based overrides directory: <TICKER>.yaml (spec §7.6).",
    )
    industry_mapping_path: Path | None = Field(
        default=None,
        description=(
            "Optional CSV mapping provider industry labels to the Damodaran taxonomy "
            "(spec §4.3.1). Unset uses the mapping shipped with the package."
        ),
    )
    notifier: Literal["email", "telegram", "none"] = Field(
        default="none",
        description=(
            "Optional push of alerts.md after `bot portfolio`: 'email' (needs BOT_SMTP_HOST, "
            "BOT_SMTP_FROM, BOT_SMTP_TO), 'telegram' (needs BOT_TELEGRAM_BOT_TOKEN and "
            "BOT_TELEGRAM_CHAT_ID), or 'none' (default)."
        ),
    )
    smtp_host: str = Field(default="", description="SMTP server host. Required only when BOT_NOTIFIER=email.")
    smtp_port: int = Field(default=587, description="SMTP server port (587 for starttls, 465 for ssl).")
    smtp_security: Literal["starttls", "ssl", "none"] = Field(
        default="starttls",
        description="SMTP transport security. 'none' is refused when BOT_SMTP_USERNAME is set.",
    )
    smtp_username: str = Field(
        default="", description="SMTP login user. Optional; leave blank for unauthenticated relays."
    )
    smtp_password: str = Field(default="", description="SMTP login password. Used only with BOT_SMTP_USERNAME.")
    smtp_from: str = Field(default="", description="Sender address. Required only when BOT_NOTIFIER=email.")
    smtp_to: str = Field(
        default="",
        description="Comma-separated recipient addresses. Required only when BOT_NOTIFIER=email.",
    )
    telegram_bot_token: str = Field(
        default="", description="Telegram bot token from @BotFather. Required only when BOT_NOTIFIER=telegram."
    )
    telegram_chat_id: str = Field(
        default="", description="Telegram chat id to message. Required only when BOT_NOTIFIER=telegram."
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")

    @field_validator("ibkr_flex_tz")
    @classmethod
    def _known_flex_tz(cls, value: str) -> str:
        """Reject a time zone name the tz database does not know."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError(f"unknown time zone {value!r} (use an IANA name such as America/New_York)") from None
        return value

    @field_validator("notifier", mode="before")
    @classmethod
    def _blank_notifier_is_none(cls, value: object) -> object:
        """Treat ``BOT_NOTIFIER=`` as the default ``none``."""
        if isinstance(value, str) and not value.strip():
            return "none"
        return value

    @field_validator("industry_mapping_path", "ibkr_flex_token_expires", mode="before")
    @classmethod
    def _blank_path_is_unset(cls, value: object) -> object:
        """Treat a blank env var as "not configured" for these optional settings.

        ``BOT_IBKR_FLEX_TOKEN_EXPIRES=`` is an unset expiry date.
        For ``BOT_INDUSTRY_MAPPING_PATH=``: without this, an empty or whitespace
        env var coerces to ``Path(".")``, which exists, so path resolution hands the CSV loader a *directory*.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


def load_settings() -> Settings:
    """Load settings; raises on missing required fields."""
    return Settings()  # type: ignore[call-arg]  # values supplied via env vars
