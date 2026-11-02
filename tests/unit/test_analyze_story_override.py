"""A story-file error fails its own ticker and leaves the batch going (#194)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_analyze_model_replay import _run_batch


def test_hypergrowth_without_story_fails_its_ticker_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, reports_dir = _run_batch(tmp_path, monkeypatch, "story_type: hypergrowth\n")
    assert result.exit_code == 1
    assert "AAPL: cannot value" in result.output
    assert "story" in result.output
    assert list(reports_dir.glob("*/analysis/MSFT.md"))
    assert not list(reports_dir.glob("*/analysis/AAPL.md"))
