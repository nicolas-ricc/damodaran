# ISO country codes translate to Damodaran country names: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A company whose `companies.country` is an ISO 3166 alpha-2 code (`"US"`, which is what EDGAR stores, or `"CH"` from FMP) resolves its `damodaran_country` row (`"United States"`, `"Switzerland"`) and its dataset-region override in the screener, the valuator assumptions and the analysis sector multiples.

**Architecture:** A new module, `bot.reference.countries`, is the single translation point. It holds `ISO_TO_DAMODARAN_COUNTRY` and `damodaran_country_name()`. Every reader that joins `companies.country` to `damodaran_country.country`, plus `dataset_region`, calls the function first. `companies.country` stays ISO: providers are not touched. The single-ticker and bulk loaders translate the same way, so they keep returning identical rows. The bulk loaders run no extra query.

**Tech Stack:** Python 3.12, DuckDB, structlog, pytest, mypy --strict.

**Spec:** GitHub issue #271 (`gh issue view 271 --repo nicolas-ricc/damodaran --comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- "`companies.country` stays ISO, since both providers already agree on it." `src/bot/ingest/` is not modified.
- "One translation point in `bot.reference` maps ISO alpha-2 to the Damodaran country name, and every reader that joins `companies.country` to `damodaran_country` or to the dataset-region overrides goes through it."
- "A code with no mapping keeps today's fallbacks and logs once per code. Input that is already a Damodaran name passes through unchanged."
- Out of scope: changing what providers store; non-US dataset imports; renaming the `AssumptionSource` the country tax fallback reports (#116).
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- The bulk loaders keep their query counts (`tests/unit/test_valuation_bulk_load.py` uses `CountingConn`).

## Assumptions (declared)

- **Unmapped input is returned unchanged (stripped), not `None`.** The `WHERE country = ?` lookup then misses exactly as it does today: the screener falls back to `DEFAULT_TAX_RATE` / `DEFAULT_REGION`, and the valuator's country row is `None`. "keeps today's fallbacks" therefore holds by construction.
- **Normalisation.** The input is stripped. A two-letter input is matched upper-cased (`"us"` → `"United States"`). Any other input that is a value of the mapping passes through as-is. `None` → `None`. An empty or whitespace-only string → `None` (today, such a value matches no row either).
- **Log once per code.** `log.warning("reference.country_unmapped", country=<stripped input>)`, logged once per process per distinct stripped input through a module-level `set[str]`. This mirrors the `warned` set idiom in `assumptions._warn_uncovered`, without threading a parameter through every caller. The bot is a CLI, so one process is one run.
- **Mapping source.** Its values are exactly the 178 country names in `tests/fixtures/damodaran/ctryprem_sample.xls` (the January 2026 sheet, `parse_country_xls` with `DEFAULT_COUNTRY_COLUMN_MAP`), minus three sub-national UAE emirates that have no ISO alpha-2 code: `"Abu Dhabi"`, `"Ras Al Khaimah (Emirate of)"` and `"Sharjah"`. They are listed in `SUBNATIONAL_SHEET_ROWS`. `"AE"` maps to `"United Arab Emirates"`. That leaves 175 codes. Territories with their own alpha-2 code (HK, MO, TW, GG, JE, IM, BM, KY, CW, SX, …) map to their own rows.
- **"a code a known provider can emit".** The known providers are EDGAR (always `"US"`, `src/bot/ingest/sec_edgar.py:163,416`) and FMP (the profile's `country`, ISO alpha-2). The test reads EDGAR's code from `parse_submissions_info(...)` and `parse_company_facts(...)`. It reads FMP's codes from every `"country": "XX"` recorded in `tests/fixtures/cassettes/**/*.yaml` (today CH, DE, JP and US). It asserts that each one maps. FMP can emit any ISO country, so the sheet-coverage test is what bounds the domain.
- **`dataset_region` translates internally**, so `dataset_region("CN", None) == "China"`. Callers that already pass a translated name hit the pass-through.
- **Docs.** CONTEXT.md gains a glossary entry, **Company country**. The `regions.py` module docstring gains one line pointing at `countries.py`. The pipeline boards (`docs/pipeline/*.d2`) are not edited: their labels describe the lookup at a level this fix does not change, and `check.py` only checks that cited symbols exist, which they still do.
- **Plan location `docs/plans/`** follows the recent issue plans.

## Acceptance criteria → tests

| Criterion | Test |
|---|---|
| `country='US'`, 'United States' tax 0.25 → screener tax 0.25 | `tests/unit/test_country_iso_lookups.py::test_screener_tax_rate_for_iso_us` and `::test_screener_region_for_iso_jp` |
| Valuator resolves the country row: ERP present, tax fallback when the sector has no tax | `::test_valuator_country_row_for_iso_us`, `::test_valuator_tax_falls_back_to_iso_country` |
| Single-ticker and bulk give identical country rows | `::test_single_and_bulk_assumption_country_rows_match`, `::test_single_and_bulk_sector_multiples_match` |
| `dataset_region` resolves CN, IN and JP | `tests/unit/test_reference_regions.py::test_iso_codes_resolve_their_own_dataset` |
| Mapping covers US plus every sheet country; a provider code without a mapping fails a test | `tests/unit/test_reference_countries.py::test_every_sheet_country_has_an_iso_code`, `::test_every_known_provider_code_is_mapped` |
| Unmapped code keeps the defaults and does not raise | `test_reference_countries.py::test_unmapped_code_passes_through_and_logs_once` plus `test_country_iso_lookups.py::test_unmapped_code_keeps_screener_defaults` |
| An e2e or integration fixture seeds `country='US'` | `tests/e2e/test_pipeline.py` (`country="US"`) and `tests/integration/test_damodaran_import.py::_seed_us_software_company` |

## Review Focus

1. **Lower-case or padded ISO input (`" us"`).** It resolves like `"US"`: `test_normalises_case_and_whitespace`.
2. **A Damodaran name that is also two letters?** None exists. Every value is longer than two characters, so the upper-casing never hits a name: `test_no_damodaran_name_is_two_letters`.
3. **Bulk loaders with a mix of ISO and name-coded companies.** Each company resolves its own row. The equivalence tests seed `US`, `JP` and `United States` side by side.
4. **Repeated unmapped code across many companies (the bulk path).** One warning, not one per company: the log-once test calls the function three times.
5. **Typos in the mapping values.** Every value must be a sheet name: `test_every_mapping_value_is_a_sheet_country`.

---

### Task 1: `bot.reference.countries`

**Files:**
- Create: `src/bot/reference/countries.py`
- Test: `tests/unit/test_reference_countries.py` (written in stage 3, already failing)

**Interfaces:**
- Produces: `ISO_TO_DAMODARAN_COUNTRY: dict[str, str]`, `SUBNATIONAL_SHEET_ROWS: frozenset[str]`, `damodaran_country_name(country: str | None) -> str | None`.

- [ ] **Step 1: Run the stage-3 tests to see them fail.** Run: `uv run pytest tests/unit/test_reference_countries.py -q`. Expected: ImportError.
- [ ] **Step 2: Write the module.** It needs a docstring that explains the two vocabularies (ISO on `companies`, names on `damodaran_country`) and why the module is the one translation point. `log = get_logger(__name__)` (from `bot.utils.logging`). The mapping, verbatim:

```python
ISO_TO_DAMODARAN_COUNTRY: dict[str, str] = {
    "AD": "Andorra (Principality of)", "AE": "United Arab Emirates", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AR": "Argentina", "AT": "Austria", "AU": "Australia",
    "AW": "Aruba", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria",
    "BH": "Bahrain", "BJ": "Benin", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia",
    "BR": "Brazil", "BS": "Bahamas", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize",
    "CA": "Canada", "CD": "Congo (Democratic Republic of)", "CG": "Congo (Republic of)",
    "CH": "Switzerland", "CI": "Côte d'Ivoire", "CK": "Cook Islands", "CL": "Chile",
    "CM": "Cameroon", "CN": "China", "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba",
    "CV": "Cape Verde", "CW": "Curacao", "CY": "Cyprus", "CZ": "Czech Republic",
    "DE": "Germany", "DK": "Denmark", "DO": "Dominican Republic", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "ES": "Spain", "ET": "Ethiopia",
    "FI": "Finland", "FJ": "Fiji", "FR": "France", "GA": "Gabon", "GB": "United Kingdom",
    "GE": "Georgia", "GG": "Guernsey (States of)", "GH": "Ghana", "GM": "Gambia",
    "GN": "Guinea", "GR": "Greece", "GT": "Guatemala", "GW": "Guinea-Bissau", "GY": "Guyana",
    "HK": "Hong Kong", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man", "IN": "India",
    "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JE": "Jersey (States of)",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan",
    "KH": "Cambodia", "KP": "Korea, D.P.R.", "KR": "Korea", "KW": "Kuwait",
    "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon",
    "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MD": "Moldova",
    "ME": "Montenegro", "MG": "Madagascar", "MK": "Macedonia", "ML": "Mali", "MM": "Myanmar",
    "MN": "Mongolia", "MO": "Macao", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NE": "Niger", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands",
    "NO": "Norway", "NP": "Nepal", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama",
    "PE": "Peru", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PT": "Portugal", "PY": "Paraguay", "QA": "Qatar", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SB": "Solomon Islands", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SI": "Slovenia", "SK": "Slovakia", "SL": "Sierra Leone", "SN": "Senegal", "SO": "Somalia",
    "SR": "Suriname", "SV": "El Salvador", "SX": "St. Maarten", "SY": "Syria",
    "SZ": "Swaziland", "TC": "Turks and Caicos Islands", "TG": "Togo", "TH": "Thailand",
    "TJ": "Tajikistan", "TN": "Tunisia", "TR": "Turkey", "TT": "Trinidad and Tobago",
    "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VC": "St. Vincent & the Grenadines",
    "VE": "Venezuela", "VN": "Vietnam", "YE": "Yemen, Republic", "ZA": "South Africa",
    "ZM": "Zambia", "ZW": "Zimbabwe",
}

SUBNATIONAL_SHEET_ROWS: frozenset[str] = frozenset(
    {"Abu Dhabi", "Ras Al Khaimah (Emirate of)", "Sharjah"}
)
```

  Write `damodaran_country_name` following the "Normalisation" and "Log once per code" assumptions above.
- [ ] **Step 3: Run the tests.** Run: `uv run pytest tests/unit/test_reference_countries.py -q && uv run mypy src`. Expected: PASS.
- [ ] **Step 4: Commit** `feat(#271): ISO alpha-2 to Damodaran country name mapping`.

### Task 2: `dataset_region` and the screener resolvers translate

**Files:**
- Modify: `src/bot/reference/regions.py` (`dataset_region`, the module docstring)
- Modify: `src/bot/screener/engine.py` (`_resolve_region`, `_resolve_tax_rate`)
- Test: `tests/unit/test_reference_regions.py`, `tests/unit/test_country_iso_lookups.py` (screener tests)

**Interfaces:**
- Consumes: `damodaran_country_name` (Task 1).

- [ ] **Step 1: Run the stage-3 tests to see them fail.** Run: `uv run pytest tests/unit/test_reference_regions.py tests/unit/test_country_iso_lookups.py -k "region or screener or unmapped" -q`.
- [ ] **Step 2:** In `dataset_region`, look up `COUNTRY_REGION_OVERRIDES` with `damodaran_country_name(country)`. In `_resolve_region` and `_resolve_tax_rate`, bind `name = damodaran_country_name(country)`, return the default when it is `None`, and pass `name` to the SQL and to `dataset_region`.
- [ ] **Step 3: Run the tests.** Same command; expected PASS.
- [ ] **Step 4: Commit** `fix(#271): screener resolves ISO-coded countries`.

### Task 3: Valuator assumption loaders translate

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`_load_country`, `bulk_load_assumption_inputs`)
- Modify: `tests/integration/test_damodaran_import.py` (`_seed_us_software_company` seeds `'US'`)
- Test: `tests/unit/test_country_iso_lookups.py` (valuator tests)

**Interfaces:**
- Consumes: `damodaran_country_name` (Task 1).

- [ ] **Step 1: Run the stage-3 tests to see them fail.** Run: `uv run pytest tests/unit/test_country_iso_lookups.py -k "valuator or assumption" -q`.
- [ ] **Step 2:** `_load_country` queries with the translated name. In the bulk loader, build `names = {c.country: damodaran_country_name(c.country) ...}` once, query `damodaran_country` with the distinct non-`None` names, and look each company's row up by its translated name. That is still one query.
- [ ] **Step 3: Run the tests.** Run: `uv run pytest tests/unit/test_country_iso_lookups.py tests/unit/test_valuation_bulk_load.py tests/integration/test_damodaran_import.py -q`. Expected: PASS.
- [ ] **Step 4: Commit** `fix(#271): valuator resolves ISO-coded country rows`.

### Task 4: Analysis sector-multiples loaders translate

**Files:**
- Modify: `src/bot/valuator/analysis.py` (`_load_sector_multiples`, and the `country_rows` block in `bulk_load_valuation_inputs`, both uses)
- Test: `tests/unit/test_country_iso_lookups.py::test_single_and_bulk_sector_multiples_match`

**Interfaces:**
- Consumes: `damodaran_country_name` (Task 1).

- [ ] **Step 1: Run the stage-3 test to see it fail.**
- [ ] **Step 2:** Same pattern as Task 3: translate before the `WHERE country = ?` query, and key the bulk `country_rows` lookups (both of them, the `regions` loop and the `ValuationInput` loop) by the translated name.
- [ ] **Step 3: Run the tests.** Run: `uv run pytest tests/unit/test_country_iso_lookups.py tests/unit/test_valuation_bulk_load.py tests/unit/test_valuator_analysis.py -q`. Expected: PASS.
- [ ] **Step 4: Commit** `fix(#271): analysis sector multiples resolve ISO-coded countries`.

### Task 5: e2e fixture and docs

**Files:**
- Modify: `tests/e2e/test_pipeline.py:237` (`country="US"`, with the comment updated to say that this is the provider's ISO shape)
- Modify: `CONTEXT.md` (glossary entry **Company country**: the ISO 3166 alpha-2 code providers store, translated to Damodaran's country name by `bot.reference.countries` before any Damodaran lookup. _Avoid_: using it as a `damodaran_country` key directly.)

- [ ] **Step 1:** Make the edits.
- [ ] **Step 2: Run the full suite.** Run: `uv run ruff check . && uv run mypy src && uv run pytest -q`. Expected: all green.
- [ ] **Step 3: Commit** `test(#271): e2e seeds the ISO country providers store`.
