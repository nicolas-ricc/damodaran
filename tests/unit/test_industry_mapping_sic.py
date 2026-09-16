"""The EDGAR side of the industry mapping — SIC descriptions (EDGAR
vocabulary) to Damodaran, keyed by the provider that resolves them."""

from __future__ import annotations

import csv

from bot.ingest.industry_mapping import default_mapping_path, load_industry_mapping


def _rows() -> list[dict[str, str]]:
    with default_mapping_path().open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_edgar_rows_exist() -> None:
    assert sum(1 for r in _rows() if r["provider"] == "edgar") >= 40


def test_edgar_damodaran_labels_are_already_known_labels() -> None:
    """Guard against typos: every Damodaran label on an edgar row must
    already appear on some fmp row — fmp's right-hand side was validated
    against the damodaran_industry table when that mapping shipped."""
    rows = _rows()
    fmp_labels = {r["damodaran_industry"] for r in rows if r["provider"] == "fmp"}
    for r in rows:
        if r["provider"] != "edgar":
            continue
        assert r["damodaran_industry"] in fmp_labels, (
            f"unknown Damodaran label {r['damodaran_industry']!r} "
            f"for SIC {r['provider_industry']!r}"
        )


def test_common_sic_descriptions_resolve() -> None:
    mapping = load_industry_mapping()
    assert mapping.resolve("edgar", "Electronic Computers") is not None
    assert mapping.resolve("edgar", "Services-Prepackaged Software") is not None
    assert mapping.resolve("edgar", "Pharmaceutical Preparations") is not None
    assert mapping.resolve("edgar", "Totally Unknown Industry") is None
