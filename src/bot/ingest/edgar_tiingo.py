"""The free-stack adapter with a keyed price source: SEC EDGAR + Tiingo (ADR 0007).

The EDGAR half lives in :class:`bot.ingest.edgar_base.EdgarPricedProvider`;
this subclass supplies Tiingo's daily EOD endpoint. Unlike Stooq, Tiingo is a
plain keyed REST API whose free tier covers a full S&P 500 refresh, so this is
the recommended default price source. FX is a USD no-op (US-only scope).
"""

from __future__ import annotations

from datetime import date

import httpx

from bot.ingest.edgar_base import EdgarPricedProvider
from bot.ingest.provider import PriceBar
from bot.ingest.tiingo import TiingoClient


class EdgarTiingoProvider(EdgarPricedProvider):
    """EDGAR + Tiingo behind the provider port. One instance per bulk run."""

    def __init__(
        self,
        sec_user_agent: str,
        tiingo_api_key: str,
        timeout: float = 30.0,
        sec_transport: httpx.BaseTransport | None = None,
        tiingo_transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(sec_user_agent, timeout=timeout, sec_transport=sec_transport)
        self._tiingo_api_key = tiingo_api_key
        self._tiingo_transport = tiingo_transport
        self._tiingo: TiingoClient | None = None

    @property
    def name(self) -> str:
        return "edgar_tiingo"

    def _prices(self) -> TiingoClient:
        if self._tiingo is None:
            self._tiingo = TiingoClient(
                api_key=self._tiingo_api_key,
                timeout=self._timeout,
                transport=self._tiingo_transport,
            )
        return self._tiingo

    def _close_prices(self) -> None:
        if self._tiingo is not None:
            self._tiingo.close()
            self._tiingo = None

    def _fetch_bars(self, sym: str, since: date | None) -> list[PriceBar]:
        return self._prices().daily_prices(sym, since)
