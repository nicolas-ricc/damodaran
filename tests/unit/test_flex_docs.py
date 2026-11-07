"""The Flex docs point at the importer (#56) and at bot flex-capture as its validation step (#140)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _flex_section(readme: str) -> str:
    start = readme.index("### Portfolio sync via Flex Web Service")
    return readme[start : readme.index("\n### ", start + 1)]


def test_readme_has_the_flex_section() -> None:
    section = " ".join(_flex_section((ROOT / "README.md").read_text(encoding="utf-8")).split())
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


def test_readme_documents_the_five_flex_sections() -> None:
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    for name in ("Open Positions", "Cash Report", "Trades", "Corporate Actions", "Cash Transactions"):
        assert name in readme
    assert "Last 7 Calendar Days" in readme
    assert "BOT_IBKR_FLEX_TZ" in readme


@pytest.mark.parametrize("path", ["README.md", ".env.example"])
def test_no_tws_socket_settings_left(path: str) -> None:
    assert "BOT_IBKR_HOST" not in (ROOT / path).read_text(encoding="utf-8")


def test_adr_0004_is_superseded_by_0010() -> None:
    text = (ROOT / "docs/adr/0004-tws-api-via-ib-async.md").read_text(encoding="utf-8")
    status = text.split("## Status", 1)[1].split("##", 1)[0]
    assert "Superseded by ADR 0010" in status


def test_adr_0010_is_implemented() -> None:
    (path,) = (ROOT / "docs/adr").glob("0010-*.md")
    text = path.read_text(encoding="utf-8")
    assert "Implemented" in text.split("## Status", 1)[1].split("##", 1)[0]
