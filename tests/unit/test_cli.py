"""Unit tests for CLI helpers."""

from __future__ import annotations

from pathlib import Path

from bot.cli import _load_tickers
from bot.ingest.refresh import RefreshStats


def test_load_tickers_plain_csv(tmp_path: Path) -> None:
    csv = tmp_path / "universe.csv"
    csv.write_text("ticker\nAAPL\nMSFT\n")
    assert _load_tickers(csv) == ["AAPL", "MSFT"]


def test_load_tickers_bom_csv(tmp_path: Path) -> None:
    """CSV saved by Excel often has a UTF-8 BOM; the first ticker must not gain a BOM prefix."""
    csv = tmp_path / "universe.csv"
    csv.write_bytes("ticker\nAAPL\nMSFT\n".encode("utf-8-sig"))
    tickers = _load_tickers(csv)
    assert tickers == ["AAPL", "MSFT"], f"Got {tickers!r}; BOM not stripped"


def test_load_tickers_strips_whitespace(tmp_path: Path) -> None:
    csv = tmp_path / "universe.csv"
    csv.write_text("ticker\n  aapl  \nMSFT\n")
    assert _load_tickers(csv) == ["AAPL", "MSFT"]


def test_refresh_stats_fail_rate_boundary() -> None:
    """At exactly 5% fail rate the status is 'partial', not 'success'."""
    stats = RefreshStats(total=20, errors=1)
    assert stats.fail_rate == 0.05
    assert stats.status == "partial"


def test_refresh_stats_below_threshold_is_success() -> None:
    stats = RefreshStats(total=100, errors=4)
    assert stats.fail_rate == 0.04
    assert stats.status == "success"
