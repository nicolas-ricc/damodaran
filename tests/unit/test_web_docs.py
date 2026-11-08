"""The docs record the web viewer (issues #92, #261)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

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


def _synthwave_colours() -> dict[str, str]:
    css = (_ROOT / "src" / "bot" / "web" / "static" / "theme.css").read_text()
    colours = dict(re.findall(r"--color-([a-z0-9-]+):\s*([^;]+);", css))
    assert len(colours) == 20
    return colours


def _design_frontmatter() -> dict[str, object]:
    text = (_ROOT / "docs" / "DESIGN.md").read_text()
    _, front, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(front)
    assert isinstance(loaded, dict)
    return loaded


def test_design_md_frontmatter_parses() -> None:
    colors = _design_frontmatter()["colors"]
    assert isinstance(colors, dict)
    assert len(colors) == 20
    assert colors == _synthwave_colours()


def test_design_md_describes_the_daisyui_system() -> None:
    text = (_ROOT / "docs" / "DESIGN.md").read_text()
    assert "synthwave" in text
    assert "DaisyUI" in text
    assert "primary" in text
    for value in _synthwave_colours().values():
        assert value in text
    for word in ("Rim", "Night Ledger", "ember", "paper-well", "kraft"):
        assert word not in text


def test_adr_0011_is_accepted_and_implemented() -> None:
    adrs = list((_ROOT / "docs" / "adr").glob("0011-*.md"))
    assert len(adrs) == 1
    text = adrs[0].read_text()
    for needle in ("Accepted", "Implemented", "vendor_daisyui.sh", "theme.css"):
        assert needle in text


def test_adr_0008_notes_the_supersession() -> None:
    adrs = list((_ROOT / "docs" / "adr").glob("0008-*.md"))
    assert len(adrs) == 1
    assert "ADR 0011" in adrs[0].read_text()
