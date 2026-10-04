"""The docs record the web viewer (issue #92)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_adr_0008_is_implemented() -> None:
    adrs = list((_ROOT / "docs" / "adr").glob("0008-*.md"))
    assert len(adrs) == 1
    assert "Implemented" in adrs[0].read_text()


def test_context_defines_verdict() -> None:
    assert "**Verdict**" in (_ROOT / "CONTEXT.md").read_text()


def test_readme_documents_the_site_flow() -> None:
    readme = (_ROOT / "README.md").read_text()
    assert "bot site" in readme
    assert "reports/*/analysis/*.json" in readme


def test_product_and_main_spec_admit_the_viewer() -> None:
    assert "0008" in (_ROOT / "docs" / "PRODUCT.md").read_text()
    spec = (_ROOT / "docs/superpowers/specs/2026-05-25-investment-bot-design.md").read_text()
    section_15 = spec[spec.index("## 15.") :]
    assert "0008" in section_15


def test_estado_inventories_the_viewer() -> None:
    assert "web/site.py" in (_ROOT / "docs" / "plano" / "estado.py").read_text()
