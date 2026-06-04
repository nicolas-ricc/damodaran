"""Unit tests for import_company_from_sec (Block 3 hardening).

Covers:
- Fix 1: if the shared _log_refresh raises, import_company_from_sec still returns
  the IngestResult instead of propagating the exception.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from bot.ingest.base import IngestResult
from bot.ingest.sec_edgar import import_company_from_sec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_FACTS: dict[str, Any] = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {"us-gaap": {}},
}


def _make_mock_conn() -> MagicMock:
    """Return a mock DuckDB connection that accepts execute calls."""
    conn = MagicMock()
    conn.execute.return_value = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# Fix 1 — _log_refresh failure must not crash the importer
# ---------------------------------------------------------------------------


def test_import_company_returns_result_even_when_log_insert_fails() -> None:
    """If the shared _log_refresh raises, import_company_from_sec must swallow the
    exception and still return a valid IngestResult (success or error)."""
    conn = _make_mock_conn()

    with (
        patch(
            "bot.ingest.base._log_refresh",
            side_effect=RuntimeError("DB closed — cannot insert refresh log"),
        ),
        patch(
            "bot.ingest.sec_edgar.SecEdgarClient.lookup_cik",
            return_value="0000320193",
        ),
        patch(
            "bot.ingest.sec_edgar.SecEdgarClient.fetch_company_facts",
            return_value=MINIMAL_FACTS,
        ),
    ):
        result = import_company_from_sec(
            conn,
            ticker="AAPL",
            user_agent="Test User test@example.com",
        )

    assert isinstance(result, IngestResult), (
        "import_company_from_sec must return an IngestResult even when _log_refresh_sec raises"
    )
    assert result.source == "sec_edgar"
    assert result.status in {"success", "error"}
