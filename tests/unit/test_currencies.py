"""The curated per-currency risk-free / nominal-GDP table (ADR 0005 §4, #109).

``config/currencies.yaml`` is hand-curated: Damodaran's January table of
risk-free rates by currency (government bond rate net of the rating-based
default spread) and IMF WEO nominal-GDP growth. The loader is a pure
``path -> mapping`` function that degrades to an empty mapping when the file is
missing or malformed (spec §13.2) and fails loudly on out-of-range values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.config import Settings
from bot.reference.currencies import CurrencyRates, load_currency_table, normalize_currency

REPO_FILE = Path(__file__).resolve().parents[2] / "config" / "currencies.yaml"

MAJORS = {"USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "CNY", "INR", "BRL"}

_ROW = (
    "  risk_free_rate: {rfr}\n"
    "  nominal_gdp_growth: {gdp}\n"
    "  source: https://example.org/rfr\n"
    "  gdp_source: https://example.org/gdp\n"
    "  as_of: 2026-01-01\n"
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "currencies.yaml"
    path.write_text(text)
    return path


def test_seeded_file_has_the_ten_major_currencies() -> None:
    assert set(load_currency_table(REPO_FILE)) >= MAJORS


def test_every_seeded_row_has_sources_and_as_of() -> None:
    for code, rates in load_currency_table(REPO_FILE).items():
        assert rates.source.startswith("https://"), code
        assert rates.gdp_source.startswith("https://"), code
        assert isinstance(rates.as_of, date), code


def test_seeded_usd_and_jpy_values() -> None:
    table = load_currency_table(REPO_FILE)
    assert (table["USD"].risk_free_rate, table["USD"].nominal_gdp_growth) == pytest.approx(
        (0.0395, 0.04)
    )
    assert (table["JPY"].risk_free_rate, table["JPY"].nominal_gdp_growth) == pytest.approx(
        (0.0147, 0.0261)
    )


def test_loads_a_valid_row(tmp_path: Path) -> None:
    table = load_currency_table(_write(tmp_path, "JPY:\n" + _ROW.format(rfr=0.0147, gdp=0.0261)))
    assert table["JPY"] == CurrencyRates(
        risk_free_rate=0.0147,
        nominal_gdp_growth=0.0261,
        source="https://example.org/rfr",
        gdp_source="https://example.org/gdp",
        as_of=date(2026, 1, 1),
    )


def test_missing_file_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_currency_table(tmp_path / "absent.yaml")
    assert dict(table) == {}
    assert [e["event"] for e in logs].count("currencies.absent") == 1


@pytest.mark.parametrize(
    "text",
    [
        "USD: [unclosed\n",
        "- USD\n- EUR\n",
        "usd:\n" + _ROW.format(rfr=0.0395, gdp=0.04),
        "USD:\n  risk_free_rate: 0.0395\n  nominal_gdp_growth: 0.04\n"
        "  source: https://example.org/rfr\n  gdp_source: https://example.org/gdp\n",
    ],
    ids=["unparsable", "not-a-mapping", "lowercase-key", "missing-as_of"],
)
def test_malformed_file_warns_and_is_empty(tmp_path: Path, text: str) -> None:
    with capture_logs() as logs:
        table = load_currency_table(_write(tmp_path, text))
    assert dict(table) == {}
    assert "currencies.malformed" in [e["event"] for e in logs]


@pytest.mark.parametrize(
    ("rfr", "gdp"),
    [(3.95, 0.04), (0.30, 0.04), (-0.05, 0.04), (0.0395, 0.25), (0.0395, -0.05)],
)
def test_out_of_range_value_fails_at_load(tmp_path: Path, rfr: float, gdp: float) -> None:
    with pytest.raises(ValueError):
        load_currency_table(_write(tmp_path, "USD:\n" + _ROW.format(rfr=rfr, gdp=gdp)))


def test_table_is_immutable(tmp_path: Path) -> None:
    table = load_currency_table(_write(tmp_path, "USD:\n" + _ROW.format(rfr=0.0395, gdp=0.04)))
    with pytest.raises(TypeError):
        table["EUR"] = table["USD"]  # type: ignore[index]


def test_normalize_currency() -> None:
    assert normalize_currency(" usd ") == "USD"
    assert normalize_currency("") is None
    assert normalize_currency(None) is None


def test_settings_currencies_path_default_and_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "test test@example.com")
    monkeypatch.delenv("BOT_CURRENCIES_PATH", raising=False)
    assert Settings(_env_file=None).currencies_path == Path("./config/currencies.yaml")  # type: ignore[call-arg]
    monkeypatch.setenv("BOT_CURRENCIES_PATH", str(tmp_path / "c.yaml"))
    assert Settings(_env_file=None).currencies_path == tmp_path / "c.yaml"  # type: ignore[call-arg]


def test_unreadable_path_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_currency_table(tmp_path)  # a directory, not a file
    assert dict(table) == {}
    assert "currencies.malformed" in [e["event"] for e in logs]


def test_duplicate_currency_key_is_malformed(tmp_path: Path) -> None:
    text = "USD:\n" + _ROW.format(rfr=0.0395, gdp=0.04) + "USD:\n" + _ROW.format(rfr=0.05, gdp=0.04)
    with capture_logs() as logs:
        table = load_currency_table(_write(tmp_path, text))
    assert dict(table) == {}
    assert "currencies.malformed" in [e["event"] for e in logs]


def test_datetime_as_of_is_narrowed_to_date(tmp_path: Path) -> None:
    text = "USD:\n" + _ROW.format(rfr=0.0395, gdp=0.04).replace(
        "as_of: 2026-01-01", "as_of: 2026-01-01T00:00:00"
    )
    as_of = load_currency_table(_write(tmp_path, text))["USD"].as_of
    assert type(as_of) is date
