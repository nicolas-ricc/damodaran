"""Pins which cassettes are synthetic (hand-authored) to SYNTHETIC.txt."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"


def _listed(root: Path) -> set[str]:
    return {
        line.strip() for line in (root / "SYNTHETIC.txt").read_text().splitlines() if line.strip()
    }


def _headed(root: Path) -> set[str]:
    out = set()
    for path in root.rglob("*.yaml"):
        with path.open() as fh:
            if "SYNTHETIC" in fh.readline():
                out.add(path.relative_to(root).as_posix())
    return out


def test_synthetic_headers_match_allowlist() -> None:
    assert _headed(CASSETTES) == _listed(CASSETTES)


def test_allowlist_holds_only_fmp_cassettes() -> None:
    assert all(p.startswith(("fmp/", "universe/")) for p in _listed(CASSETTES))


@pytest.mark.parametrize("entry", sorted(_listed(CASSETTES)))
def test_dropping_a_header_breaks_the_match(tmp_path: Path, entry: str) -> None:
    root = tmp_path / "cassettes"
    shutil.copytree(CASSETTES, root)
    target = root / entry
    target.write_text(target.read_text().split("\n", 1)[1])
    assert _headed(root) != _listed(root)


def test_unlisted_synthetic_cassette_breaks_the_match(tmp_path: Path) -> None:
    root = tmp_path / "cassettes"
    shutil.copytree(CASSETTES, root)
    (root / "fmp" / "extra.yaml").write_text("# SYNTHETIC cassette\ninteractions: []\n")
    assert _headed(root) != _listed(root)


def test_header_below_first_line_is_not_synthetic(tmp_path: Path) -> None:
    (tmp_path / "SYNTHETIC.txt").write_text("")
    (tmp_path / "a.yaml").write_text("interactions: []\n# SYNTHETIC\n")
    assert _headed(tmp_path) == set()
