"""The free-stack adapter: SEC EDGAR fundamentals + Stooq EOD prices (ADR 0007).

The EDGAR half lives in :class:`bot.ingest.edgar_base.EdgarPricedProvider`;
this subclass supplies the Stooq price source. Stooq's HTTP endpoint is behind
an anti-bot wall, so a directory of CSVs harvested by
``scripts/stooq_browser_fetch.mjs`` (``stooq_dir``) is the working path; the
HTTP client remains for if the wall ever comes down. FX is a USD no-op: this
adapter exists only under the US-only scope.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

from bot.ingest.edgar_base import EdgarPricedProvider
from bot.ingest.provider import PriceBar
from bot.ingest.stooq import StooqClient, parse_stooq_csv


class EdgarStooqProvider(EdgarPricedProvider):
    """EDGAR + Stooq behind the provider port. One instance per bulk run."""

    def __init__(
        self,
        sec_user_agent: str,
        timeout: float = 30.0,
        sec_transport: httpx.BaseTransport | None = None,
        stooq_transport: httpx.BaseTransport | None = None,
        stooq_dir: Path | None = None,
    ) -> None:
        super().__init__(sec_user_agent, timeout=timeout, sec_transport=sec_transport)
        self._stooq_transport = stooq_transport
        self._stooq_dir = stooq_dir
        self._stooq: StooqClient | None = None

    @property
    def name(self) -> str:
        return "edgar_stooq"

    def _prices(self) -> StooqClient:
        if self._stooq is None:
            self._stooq = StooqClient(timeout=self._timeout, transport=self._stooq_transport)
        return self._stooq

    def _close_prices(self) -> None:
        if self._stooq is not None:
            self._stooq.close()
            self._stooq = None

    def _bars_from_dir(self, sym: str, since: date | None) -> list[PriceBar]:
        """Read ``<stooq_dir>/<TICKER>.csv`` (the browser recipe's output).

        Stooq's anti-bot wall blocks the HTTP path (ADR 0007);
        ``scripts/stooq_browser_fetch.mjs`` harvests the CSVs through a real
        browser instead. A missing file is a per-ticker failure that names the
        recipe — the run continues with the other tickers.
        """
        assert self._stooq_dir is not None
        path = self._stooq_dir / f"{sym}.csv"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path}: no CSV for {sym} — harvest it first with "
                f"`node scripts/stooq_browser_fetch.mjs {sym}` (see ADR 0007)"
            )
        bars = parse_stooq_csv(path.read_text(encoding="utf-8"))
        if since is not None:
            bars = [b for b in bars if b.date >= since]
        return bars

    def _fetch_bars(self, sym: str, since: date | None) -> list[PriceBar]:
        if self._stooq_dir is not None:
            return self._bars_from_dir(sym, since)
        return self._prices().daily_prices(sym, since)
