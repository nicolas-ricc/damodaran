"""The README describes how the price drip shares the DB lock (issue #310)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _drip_paragraph() -> str:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    start = readme.find("`scripts/daily.sh` therefore repeats")
    end = readme.find("Tiingo Power", start)
    assert -1 < start < end, "Quickstart step 3 price paragraph not found"
    return " ".join(readme[start:end].split())


def test_readme_quickstart_says_the_drip_skips_on_the_shared_lock() -> None:
    text = _drip_paragraph()
    for fact in (
        ".cache/bot.lock",
        "skipped: DB busy",
        "Tiingo quota",
        "scripts/install_cron.sh",
        "(#108)",
    ):
        assert fact in text, fact
    assert "Tiingo quota, so the drip" in text  # the quota is why it is first-fill only
    assert "do not run both" not in text
    assert "same DuckDB file" not in text
