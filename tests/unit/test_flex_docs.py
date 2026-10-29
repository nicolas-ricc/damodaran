"""The docs that used to say corporate_actions has no writer now point at the importer (#56)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _flex_section(readme: str) -> str:
    start = readme.index("### Corporate actions via Flex Web Service")
    return readme[start : readme.index("\n### ", start + 1)]


def test_readme_has_the_flex_section() -> None:
    section = _flex_section((ROOT / "README.md").read_text(encoding="utf-8"))
    assert (
        "Written from IBKR's documentation; the parser is validated against a real statement "
        "captured with the command below. Known corrections are tracked in #111." in section
    )
    assert "uv run bot flex-capture" in section
    for path in (
        "tests/fixtures/cassettes/ibkr_flex/statement_real.yaml",
        "tests/fixtures/ibkr_flex/statement_real_redacted.xml",
        "tests/fixtures/ibkr_flex/statement_real_summary.json",
    ):
        assert path in section
    assert "BOT_IBKR_FLEX_TOKEN" in section and "BOT_IBKR_FLEX_QUERY_ID" in section


def test_readme_drops_the_see_110_wording() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "see #110" not in readme
    assert "not yet verified" not in " ".join(readme.split())


@pytest.mark.parametrize("path", ["src/bot/ingest/ibkr_flex.py", "tests/fixtures/ibkr_flex/statement_sample.xml"])
def test_flex_sources_point_at_flex_capture(path: str) -> None:
    text = " ".join((ROOT / path).read_text(encoding="utf-8").split())
    assert "not yet verified" not in text
    assert "arrives with #110" not in text
    assert "flex-capture" in text
    assert "#111" in text


def test_sample_fixture_header_has_the_capture_sentence() -> None:
    text = " ".join((ROOT / "tests/fixtures/ibkr_flex/statement_sample.xml").read_text(encoding="utf-8").split())
    assert (
        "A redacted real sample is captured with `bot flex-capture` into "
        "statement_real_redacted.xml; parser corrections land in #111." in text
    )


def test_env_example_points_at_flex_capture() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    (line,) = [entry for entry in lines if "BOT_IBKR_FLEX_QUERY_ID" in entry]
    assert line.endswith("; validate with bot flex-capture")


@pytest.mark.parametrize(
    "path",
    ["docs/adr/0004-tws-api-via-ib-async.md", "src/bot/storage/schema.sql", "src/bot/portfolio/trades.py"],
)
def test_no_more_nothing_populates_wording(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "ibkr_flex" in text
    for stale in ("nothing populates it", "stays\n  empty", "stays empty", "nothing in this module populates it"):
        assert stale not in text
