"""Country → Damodaran dataset region (spec §5.1)."""

from __future__ import annotations

from bot.reference.regions import (
    COUNTRY_REGION_OVERRIDES,
    DATASET_REGIONS,
    GEOGRAPHIC_TO_DATASET_REGION,
    dataset_region,
)


def test_every_mapping_target_is_a_published_dataset_region() -> None:
    assert set(GEOGRAPHIC_TO_DATASET_REGION.values()) <= DATASET_REGIONS
    assert set(COUNTRY_REGION_OVERRIDES.values()) <= DATASET_REGIONS


def test_covers_every_grouping_the_published_file_uses() -> None:
    # The nine groupings present in the Moody's-rated table of ctryprem.xls.
    assert set(GEOGRAPHIC_TO_DATASET_REGION) == {
        "Africa",
        "Asia",
        "Australia & New Zealand",
        "Caribbean",
        "Central and South America",
        "Eastern Europe & Russia",
        "Middle East",
        "North America",
        "Western Europe",
    }


def test_united_states_resolves_to_the_us_dataset() -> None:
    assert dataset_region("United States", "North America") == "US"


def test_western_europe_resolves_to_europe() -> None:
    assert dataset_region("Germany", "Western Europe") == "Europe"


def test_country_override_beats_its_grouping() -> None:
    # Japan, China and India each have their own published dataset, so their
    # Asia grouping must not send them to EM.
    assert dataset_region("Japan", "Asia") == "Japan"
    assert dataset_region("China", "Asia") == "China"
    assert dataset_region("India", "Asia") == "India"
    # An unlisted Asian country still goes to EM.
    assert dataset_region("Thailand", "Asia") == "EM"


def test_unknown_grouping_falls_back_to_us() -> None:
    assert dataset_region("Atlantis", "Nowhere") == "US"


def test_missing_inputs_fall_back_to_us() -> None:
    assert dataset_region(None, None) == "US"
    assert dataset_region("United States", None) == "US"


def test_numeric_region_string_falls_back_rather_than_matching() -> None:
    # Defence in depth: even if a corrupt PRS score reached the column, it must
    # not resolve to a dataset region.
    assert dataset_region("Algeria", "67.0") == "US"
