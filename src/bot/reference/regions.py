"""Country → Damodaran dataset region.

Two different taxonomies share the word "region" and conflating them silently
broke every sector lookup in the bot:

- **Dataset region** — which of Damodaran's regional file sets a row came from.
  This is what ``damodaran_industry.region`` holds, injected from the
  ``--region`` flag at import time.
- **Geographic grouping** — the ``ERPs by country`` sheet's own column, with
  values like ``"Western Europe"`` and ``"Middle East"``. This is what
  ``damodaran_country.region`` holds.

The consumers need the first but were reading the second, so
``WHERE industry = ? AND region = ?`` never matched and every company resolved
no sector row at all. This module is the single translation point.

Only the US dataset is ingested today (``import_damodaran`` downloads the US
files regardless of ``--region`` — a separate known defect), so a non-US company
resolves a dataset region that has no rows. The valuator handles that by
substituting an available region and labelling the assumption
``sector_default_damodaran_cross_region`` so the report discloses it, rather
than silently presenting another region's medians as the company's own.
"""

from __future__ import annotations

#: The regional file sets Damodaran publishes.
DATASET_REGIONS: frozenset[str] = frozenset(
    {"US", "Europe", "EM", "Japan", "China", "India", "AusNZCanada", "Global"}
)

#: Default when a country's grouping cannot be resolved. The US set is the most
#: complete and is the only one currently ingested.
DEFAULT_DATASET_REGION = "US"

#: The nine groupings the published ``ERPs by country`` table uses, mapped to the
#: dataset that covers them.
GEOGRAPHIC_TO_DATASET_REGION: dict[str, str] = {
    "North America": "US",
    "Western Europe": "Europe",
    "Eastern Europe & Russia": "EM",
    "Asia": "EM",
    "Central and South America": "EM",
    "Caribbean": "EM",
    "Africa": "EM",
    "Middle East": "EM",
    "Australia & New Zealand": "AusNZCanada",
}

#: Countries with their own published dataset, which their grouping would
#: otherwise send to EM.
COUNTRY_REGION_OVERRIDES: dict[str, str] = {
    "China": "China",
    "India": "India",
    "Japan": "Japan",
}


def dataset_region(country: str | None, geographic_region: str | None) -> str:
    """Resolve the Damodaran dataset region for a company's country.

    A country-level override wins over its geographic grouping; an unknown or
    malformed grouping falls back to :data:`DEFAULT_DATASET_REGION` rather than
    resolving to nothing, so a sector lookup always has a region to try.
    """
    if country is not None:
        override = COUNTRY_REGION_OVERRIDES.get(country.strip())
        if override is not None:
            return override
    if geographic_region is not None:
        mapped = GEOGRAPHIC_TO_DATASET_REGION.get(geographic_region.strip())
        if mapped is not None:
            return mapped
    return DEFAULT_DATASET_REGION
