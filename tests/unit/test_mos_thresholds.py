"""The margin-of-safety verdict thresholds are defined once (issue #220)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import bot.reporting.analysis_report as analysis_report
import bot.web.views as views
from bot.reporting.analysis_report import MOS_FAIR, MOS_UNDERVALUED, margin_verdict

_SRC = Path(__file__).resolve().parents[2] / "src"
_PACKAGES = (_SRC / "bot" / "reporting", _SRC / "bot" / "web")
_HOME = _SRC / "bot" / "reporting" / "analysis_report.py"
_TOKEN = re.compile(r"(?<![\d.])1\.3(?![\d])")
_RULE = (
    "MoS thresholds live in bot.reporting.analysis_report; import MOS_UNDERVALUED/MOS_FAIR. "
    "A 1.3 that is not a MoS threshold needs an exemption in this test."
)


def _sources(*suffixes: str) -> list[Path]:
    return sorted(p for pkg in _PACKAGES for p in pkg.rglob("*") if p.suffix in suffixes)


def test_margin_verdict_reads_the_constants() -> None:
    assert margin_verdict(MOS_UNDERVALUED) == "potentially undervalued"
    assert margin_verdict(MOS_UNDERVALUED - 1e-9) == "around fair value"
    assert margin_verdict(MOS_FAIR) == "around fair value"
    assert margin_verdict(MOS_FAIR - 1e-9) == "potentially overvalued"


def test_threshold_values_unchanged() -> None:
    assert (MOS_UNDERVALUED, MOS_FAIR) == (1.3, 1.0)


def test_views_reexports_the_report_constants() -> None:
    assert views.MOS_UNDERVALUED is analysis_report.MOS_UNDERVALUED
    assert views.MOS_FAIR is analysis_report.MOS_FAIR
    assert views.VERDICT_TEXT[views.Verdict.UNDERVALUED] == margin_verdict(MOS_UNDERVALUED)
    assert views.VERDICT_TEXT[views.Verdict.FAIR] == margin_verdict(MOS_FAIR)


def test_thresholds_defined_once() -> None:
    found: dict[str, list[str]] = {"MOS_UNDERVALUED": [], "MOS_FAIR": []}
    for path in _sources(".py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            for target in targets:
                if isinstance(target, ast.Name) and target.id in found:
                    found[target.id].append(str(path.relative_to(_SRC)))
    home = str(_HOME.relative_to(_SRC))
    assert found == {"MOS_UNDERVALUED": [home], "MOS_FAIR": [home]}, _RULE


def test_no_other_mos_literal() -> None:
    hits = [
        f"{path.relative_to(_SRC)}:{number}: {line.strip()}"
        for path in _sources(".py", ".j2", ".html")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _TOKEN.search(line)
    ]
    assert len(hits) == 1, f"{_RULE}\n" + "\n".join(hits)
    assert hits[0].startswith("bot/reporting/analysis_report.py:"), hits[0]
    assert "MOS_UNDERVALUED = 1.3" in hits[0], hits[0]
