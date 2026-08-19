"""The shipped default universe must be the real S&P 500, in FMP ticker format."""

from bot.ingest.universe import default_universe_path, load_universe


def test_default_universe_is_real_sp500() -> None:
    tickers = load_universe(default_universe_path())
    assert 490 <= len(tickers) <= 510
    # Miembros permanentes que detectan un archivo sintético o truncado.
    for known in ("AAPL", "MSFT", "JNJ", "JPM", "XOM"):
        assert known in tickers
    # Formato FMP: guion, nunca punto (BRK.B -> BRK-B).
    assert "BRK-B" in tickers
    assert not any("." in t for t in tickers)


def test_default_universe_has_no_duplicates() -> None:
    tickers = load_universe(default_universe_path())
    assert len(tickers) == len(set(tickers))
