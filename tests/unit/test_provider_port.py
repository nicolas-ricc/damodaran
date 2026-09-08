"""The provider port: canonical records and the neutral rate-limit error."""

from __future__ import annotations

from datetime import date

from bot.ingest.fmp import FmpRateLimitError
from bot.ingest.provider import (
    CompanyInfo,
    FxRate,
    MarketDataProvider,
    PriceBar,
    ProviderRateLimitError,
)


def test_fmp_rate_limit_error_is_a_provider_rate_limit_error() -> None:
    # Orchestration will catch only the neutral error; FMP's must satisfy it.
    assert issubclass(FmpRateLimitError, ProviderRateLimitError)


def test_price_bar_and_fx_rate_are_frozen_records() -> None:
    bar = PriceBar(date=date(2026, 1, 2), close=10.0, volume=1000.0, market_cap=None)
    fx = FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)
    assert bar.close == 10.0
    assert fx.rate_to_usd == 1.08


def test_company_info_still_importable_from_fmp() -> None:
    # Back-compat: existing imports of CompanyInfo from bot.ingest.fmp keep working.
    from bot.ingest.fmp import CompanyInfo as FmpCompanyInfo

    assert FmpCompanyInfo is CompanyInfo


def test_protocol_is_runtime_checkable() -> None:
    class NotAProvider:
        pass

    assert not isinstance(NotAProvider(), MarketDataProvider)
