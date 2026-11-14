"""Company profiles in the viewer: detail page, search and `bot site` (issue #333)."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from bot.cli import app
from bot.reference.company_profiles import CompanyProfile, IndustryTag, ProfileTag
from bot.web.index import AnalysisRef
from bot.web.site import build
from bot.web.views import profile_view, row_view, search_tags
from tests.web_sidecars import make_sidecar, write_sidecar

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "src" / "bot" / "web" / "static" / "viewer.js"
_DAISYUI = _ROOT / "src" / "bot" / "web" / "static" / "daisyui.css"

_CYBER = IndustryTag("cybersecurity", "Cybersecurity", "Software that stops intrusions.")
_CLOUD = IndustryTag("cloud-infrastructure", "Cloud infrastructure", "Rented compute.")


def _crwd(description: str = "Sells endpoint security software.") -> CompanyProfile:
    return CompanyProfile(
        ticker="AAA",
        description=description,
        fiscal_year=2026,
        accession="0001535527-26-000012",
        tags=(
            ProfileTag(_CYBER, 0.95, "segment"),
            ProfileTag(_CLOUD, 0.30, "judgment"),
        ),
    )


@pytest.fixture
def reports(tmp_path: Path) -> Path:
    root = tmp_path / "reports"
    write_sidecar(root, "2026-10-01", make_sidecar("AAA", mos=1.5))
    write_sidecar(root, "2026-10-01", make_sidecar("BBB", mos=0.7))
    return root


# --- view-models -----------------------------------------------------------


def test_profile_view_words_the_share_and_source() -> None:
    view = profile_view(_crwd())
    assert view is not None
    assert view.description == "Sells endpoint security software."
    assert [t.label for t in view.tags] == ["Cybersecurity", "Cloud infrastructure"]
    assert view.tags[0].tooltip == (
        "Software that stops intrusions. ~95% of revenue, reported segment, FY2026."
    )
    assert view.tags[1].tooltip.endswith("~30% of revenue, estimated from the 10-K, FY2026.")


def test_profile_view_words_a_disaggregation_share() -> None:
    profile = CompanyProfile(
        "AAPL", "Phones.", 2025, "0000320193-25-000079",
        (ProfileTag(_CYBER, 0.51, "disaggregation"),),
    )
    view = profile_view(profile)
    assert view is not None
    assert view.tags[0].tooltip.endswith("~51% of revenue, revenue disaggregation, FY2025.")


def test_profile_view_of_no_profile_is_none() -> None:
    assert profile_view(None) is None


def test_search_tags_hold_slugs_and_lowercased_labels() -> None:
    text = search_tags(_crwd())
    assert "cybersecurity" in text
    assert "cloud-infrastructure" in text
    assert "cloud infrastructure" in text
    assert text == text.lower()
    assert search_tags(None) == ""


def test_row_view_carries_the_search_tags() -> None:
    payload = make_sidecar("AAA")
    ref = AnalysisRef(ticker="AAA", date=date(2026, 10, 1), data=payload)
    assert row_view(ref).tags == ""
    assert row_view(ref, _crwd()).tags == search_tags(_crwd())


# --- the built site ----------------------------------------------------------


def _profile_block(page: str) -> str:
    match = re.search(r'<div class="profile">.*?</div>', page, re.S)
    assert match is not None
    return match.group(0)


def test_detail_shows_profile_under_the_heading(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/", profiles={"AAA": _crwd()})
    for page in ("c/AAA.html", "f/AAA.html"):
        html = (out / page).read_text()
        block = _profile_block(html)
        assert "Sells endpoint security software." in block
        assert "badge" in block
        assert (
            '<abbr title="Software that stops intrusions. ~95% of revenue, reported segment, '
            'FY2026.">Cybersecurity</abbr>'
        ) in block
        assert block.index("Cybersecurity") < block.index("Cloud infrastructure")
        assert html.index("</h1>") < html.index('<div class="profile">')
        assert html.index('<div class="profile">') < html.index('class="instrument"')


def test_detail_without_profile_has_no_profile_block(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/", profiles={"AAA": _crwd()})
    assert 'class="profile"' not in (out / "c" / "BBB.html").read_text()
    bare = tmp_path / "bare"
    assert build(reports, bare, "/") == 2
    assert 'class="profile"' not in (bare / "c" / "AAA.html").read_text()


def test_profile_text_is_escaped(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/", profiles={"AAA": _crwd("AT&T <b>bold</b>")})
    html = (out / "c" / "AAA.html").read_text()
    assert "AT&amp;T &lt;b&gt;bold&lt;/b&gt;" in html
    assert "<b>bold</b>" not in html


def test_rows_carry_tags_without_showing_them(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/", profiles={"AAA": _crwd()})
    for page in ("index.html", "rows/all-mos-desc.html"):
        html = (out / page).read_text()
        rows = re.findall(r"<tr[^>]*>", html)
        tagged = [r for r in rows if "data-tags=" in r]
        assert len(tagged) == 1
        assert "cybersecurity" in tagged[0]
        cells = " ".join(re.findall(r"<td[^>]*>.*?</td>", html, re.S))
        assert "Cloud infrastructure" not in cells
        assert "cloud-infrastructure" not in cells


def test_search_box_mentions_industry(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    assert "Search by ticker, name or industry" in index
    assert 'placeholder="Ticker, name or industry"' in index


def test_badge_outline_is_in_the_precompiled_theme() -> None:
    assert ".badge-outline" in _DAISYUI.read_text()


# --- viewer.js ----------------------------------------------------------------


def test_search_matches_tags() -> None:
    script = _SCRIPT.read_text()
    body = script[script.index("function applySearch") : script.index("function announceDetail")]
    assert 'row.getAttribute("data-tags")' in body
    assert re.search(r'\(row\.getAttribute\("data-tags"\) \|\| ""\)\.indexOf\(q\)', body)
    assert "row.hidden = !!q && !inTicker && !inName && !inTags;" in body


# --- bot site -------------------------------------------------------------------


@pytest.fixture
def bare_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("BOT_"):
            monkeypatch.delenv(key)

    def boom(*_: object, **__: object) -> None:
        raise AssertionError("bot site must not load Settings")

    monkeypatch.setattr("bot.cli.load_settings", boom)
    monkeypatch.setattr("bot.cli._open_db", boom)


def _config(tmp_path: Path, tag: str = "cybersecurity") -> tuple[Path, Path]:
    tags = tmp_path / "industry_tags.yaml"
    profiles = tmp_path / "company_profiles.yaml"
    tags.write_text(
        yaml.safe_dump(
            [{"slug": "cybersecurity", "label": "Cybersecurity", "description": "Security."}]
        ),
        encoding="utf-8",
    )
    profiles.write_text(
        yaml.safe_dump(
            {
                "AAA": {
                    "description": "Sells endpoint security software.",
                    "fiscal_year": 2026,
                    "accession": "0001535527-26-000012",
                    "tags": [{"tag": tag, "share": 0.95, "source": "segment"}],
                }
            }
        ),
        encoding="utf-8",
    )
    return profiles, tags


def _site(reports: Path, out: Path, profiles: Path, tags: Path) -> list[str]:
    return [
        "site", "--out", str(out), "--reports-dir", str(reports),
        "--profiles", str(profiles), "--industry-tags", str(tags),
    ]


def test_site_shows_profiles_from_config(reports: Path, tmp_path: Path, bare_env: None) -> None:
    profiles, tags = _config(tmp_path)
    out = tmp_path / "site"
    result = CliRunner().invoke(app, _site(reports, out, profiles, tags))
    assert result.exit_code == 0, result.output
    assert "Sells endpoint security software." in (out / "c" / "AAA.html").read_text()


def test_site_without_profile_files_still_builds(
    reports: Path, tmp_path: Path, bare_env: None
) -> None:
    out = tmp_path / "site"
    args = _site(reports, out, tmp_path / "none.yaml", tmp_path / "none-tags.yaml")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "WARNING: no company profiles" in result.output
    assert 'class="profile"' not in (out / "c" / "AAA.html").read_text()


def test_site_rejects_an_invalid_profile_file(
    reports: Path, tmp_path: Path, bare_env: None
) -> None:
    profiles, tags = _config(tmp_path, tag="infosec")
    result = CliRunner().invoke(app, _site(reports, tmp_path / "site", profiles, tags))
    assert result.exit_code == 2
    assert "unknown tag" in result.output


def test_site_rejects_a_lone_profile_file(reports: Path, tmp_path: Path, bare_env: None) -> None:
    _, tags = _config(tmp_path)
    args = _site(reports, tmp_path / "site", tmp_path / "none.yaml", tags)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "need both files" in result.output
