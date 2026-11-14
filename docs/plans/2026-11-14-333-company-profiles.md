# Company profiles and industry tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every company in the default universe gets a plain-English description and industry tags (≥10% of revenue each) in two committed YAML files; the viewer's detail page shows them and its search box matches tags.

**Architecture:** A pure loader in `src/bot/reference/company_profiles.py` parses and validates `config/industry_tags.yaml` and `config/company_profiles.yaml` into frozen dataclasses (each profile tag carries its resolved vocabulary entry). `bot site` loads them once and passes a `ticker -> CompanyProfile` mapping into `bot.web.site.build`; the view-models turn a profile into a description, badges with tooltip text, and a lower-case search string the rows carry as `data-tags`. The profiles themselves are written once by agent sessions reading 10-Ks from SEC EDGAR; no bot code fetches them.

**Tech Stack:** Python 3.12, PyYAML, Jinja2, DaisyUI (precompiled, synthwave), vanilla JS (`viewer.js`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-08-company-profiles-industry-tags-design.md` (issue #333).

## Global Constraints

- A tag is given only when that business is at least ~10% of revenue: `share >= 0.10`, `share <= 1`, a company's shares sum to at most 1 (allow a float tolerance of 1e-9).
- `source` is one of `segment`, `disaggregation`, `judgment`.
- `accession` matches `^\d{10}-\d{2}-\d{6}$`.
- Tag slugs are kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`); each vocabulary entry has non-empty `slug`, `label`, `description`.
- Ticker keys use the universe's format (`BRK-B`).
- Every ticker in `src/bot/ingest/universe_default.csv` has a profile, or appears in an explicit, listed exception set.
- Tooltip wording: "~95% of revenue, reported segment, FY2026" / "~30% of revenue, estimated from the 10-K, FY2025".
- Search: case-insensitive substring over ticker, name, tag slugs and tag labels; composes with the verdict filter, the count and the no-match row unchanged; placeholder/label mentions industry.
- Tags are not displayed in the list table.
- The site stays a pure function of committed files (ADR 0008); a ticker without a profile renders without description and tags, no error.
- No `anthropic` or other LLM dependency in `pyproject.toml`.
- Do not run `ruff format` on the tree. `uv run ruff check . && uv run mypy src` and `uv run pytest -q` green.
- Styling within DaisyUI synthwave and `docs/DESIGN.md`; only classes present in the precompiled `src/bot/web/static/daisyui.css`.

## Review Focus

1. **A YAML file that is not a mapping, or an entry missing a key** (e.g. `tags:` absent, `share: "high"`): the loader raises `ProfileError` naming the ticker and the field, never a bare `KeyError`/`TypeError`. Test in Task 1.
2. **The same tag twice in one company**: rejected (it would double-count the share sum and show two identical badges). Test in Task 1.
3. **Text with HTML characters in a description or tag description** (`AT&T`, `<`): escaped on the detail page and inside the tooltip attribute. Test in Task 4.
4. **A search query that matches only a tag label word with different case** (`Cybersec`, `SEMICONDUCTOR`): matches. Test in Task 5 (data-tags is lower-cased at build time; the script lower-cases the query).
5. **`bot site` run where the config files are absent** (a checkout without `config/`, the existing CLI tests run with tmp paths): the site builds without profiles and logs a warning; a present but invalid file exits 2 with the loader's message. Test in Task 6.

---

### Task 1: Loader and validation

**Files:**
- Create: `src/bot/reference/company_profiles.py`
- Test: `tests/unit/test_company_profiles.py`

**Interfaces:**
- Produces:
  - `INDUSTRY_TAGS_PATH = Path("config/industry_tags.yaml")`, `COMPANY_PROFILES_PATH = Path("config/company_profiles.yaml")`
  - `class ProfileError(ValueError)`
  - `SOURCES: tuple[str, ...] = ("segment", "disaggregation", "judgment")`
  - `@dataclass(frozen=True) class IndustryTag: slug: str; label: str; description: str`
  - `@dataclass(frozen=True) class ProfileTag: tag: IndustryTag; share: float; source: str`
  - `@dataclass(frozen=True) class CompanyProfile: ticker: str; description: str; fiscal_year: int; accession: str; tags: tuple[ProfileTag, ...]` — tags sorted by share descending, then slug.
  - `def load_industry_tags(path: Path) -> dict[str, IndustryTag]` (keyed by slug)
  - `def load_company_profiles(path: Path, vocabulary: Mapping[str, IndustryTag]) -> dict[str, CompanyProfile]` (keyed by ticker)
  - `def load_profiles(profiles_path: Path = COMPANY_PROFILES_PATH, tags_path: Path = INDUSTRY_TAGS_PATH) -> dict[str, CompanyProfile]` — both files, vocabulary first.

File shapes: `industry_tags.yaml` is a YAML list of `{slug, label, description}` mappings. `company_profiles.yaml` is a mapping `TICKER -> {description, fiscal_year, accession, tags: [{tag, share, source}]}` (spec §6.2). Unlike `default_spreads.py`, nothing degrades silently: every defect raises `ProfileError` with the ticker (or slug) and the reason. A missing file raises `ProfileError` too (the CLI decides what absence means, Task 6).

- [ ] **Step 1: Write the failing tests** — a `_write(tmp_path, tags, profiles)` helper dumping dicts with `yaml.safe_dump`, a small vocabulary (`cybersecurity`, `smartphones`, `digital-services`), and:
  - `test_loads_a_valid_profile`: CRWD with one tag 0.95 `segment` → `profile.tags[0].tag.label == "Cybersecurity"`, `fiscal_year == 2026`, `accession == "0001535527-26-000012"`.
  - `test_tags_sorted_by_share_descending`: shares 0.10, 0.51, 0.25 → order 0.51, 0.25, 0.10.
  - parametrized `test_rejects_bad_profile` with `pytest.raises(ProfileError, match=...)` for: unknown tag `infosec` (match `"unknown tag"`), share `0.09` and `1.01` and `"high"` (match `"share"`), shares 0.6+0.5 (match `"sum"`), source `guess` (match `"source"`), `tags: []` (match `"tags"`), description `"  "` (match `"description"`), accession `0001535527-26-12` (match `"accession"`), same tag twice (match `"duplicate"`), missing `fiscal_year` (match `"fiscal_year"`), entry not a mapping (match the ticker). Each message contains the ticker.
  - parametrized `test_rejects_bad_vocabulary`: slug `Cyber Security` (not kebab), empty label, empty description, duplicate slug, file not a list.
  - `test_missing_file_raises`: `load_industry_tags(tmp_path / "nope.yaml")` raises `ProfileError`.
  - `test_share_sum_tolerates_float_noise`: 0.7 + 0.2 + 0.1 loads, and 0.34 + 0.33 + 0.33 (exactly 1.00) loads. The sum is checked on the recorded two-decimal shares.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_company_profiles.py -q` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** the module above (`yaml.safe_load`; module docstring in the style of `default_spreads.py` naming #333 and the spec).
- [ ] **Step 4: Run** the tests and `uv run mypy src` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#333): company profile and industry tag loader`.

### Task 2: Tag vocabulary

**Files:**
- Create: `config/industry_tags.yaml`
- Test: `tests/unit/test_company_profiles_committed.py`

**Interfaces:**
- Consumes: `load_industry_tags`, `INDUSTRY_TAGS_PATH` (Task 1).
- Produces: the slugs Task 3 tags with.

A fixed vocabulary of roughly 60–100 tags drafted from the universe before any company is tagged. Narrow where search needs it (`cybersecurity`, `semiconductors`, `cloud-infrastructure` are separate from generic software), broad where it does not (utilities, REITs, banks). No synonym pairs. Labels in sentence/title case as the spec's example ("Cybersecurity"); description one sentence. Coverage wins over the count: Task 3 may add tags, never variants of existing ones.

- [ ] **Step 1: Write the failing test** `test_committed_vocabulary_loads`: `tags = load_industry_tags(_ROOT / INDUSTRY_TAGS_PATH)`; `assert "cybersecurity" in tags`; `assert 40 <= len(tags) <= 150`.
- [ ] **Step 2: Run** — Expected: FAIL (file missing).
- [ ] **Step 3: Write** `config/industry_tags.yaml` with a header comment stating the ≥10% rule and pointing at the spec.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#333): industry tag vocabulary`.

### Task 3: Generate the profiles

**Files:**
- Create: `config/company_profiles.yaml`
- Modify: `config/industry_tags.yaml` (only to add a tag coverage needs)
- Test: `tests/unit/test_company_profiles_committed.py`

**Interfaces:**
- Consumes: `load_profiles`, the vocabulary (Task 2), `src/bot/ingest/universe_default.csv`.
- Produces: `config/company_profiles.yaml`, read by Task 6.

Not bot code. For each ticker: SEC EDGAR `company_tickers.json` → CIK; `submissions/CIK##########.json` → the latest `10-K` (fall back to `10-K405`/`20-F`/`40-F` only if no 10-K, and say so in the PR) → accession and the period's fiscal year (calendar year of `reportDate`, CONTEXT.md "Fiscal year"); the filing's primary document → Item 1 and the segment / revenue-disaggregation note. Write 2–3 plain sentences (what it sells, to whom; no marketing words, no valuation opinion), pick tags at ≥10% of that year's revenue, record `share` (two decimals), `source`. Batching helpers live in `.scratch/` (git-excluded) and are never committed. Batches of ~50 tickers are written to `.scratch/profiles/batch-NN.yaml` and merged in universe order into the one file, with a header comment. Fiscal year is the calendar year of the 10-K's period end (`reportDate`), CONTEXT.md "Fiscal year": a retailer whose year ends 2026-01-31 is FY2026. Before merging the batches, a scratch check confirms for every profile that its `accession` appears among the 10-K filings in that ticker's CIK `submissions` JSON and that its `fiscal_year` matches that filing's `reportDate` year (catches a mismapped CIK or an invented accession); the merge refuses a ticker in two batches. Batch files present in `.scratch/profiles/` are the progress record: an interrupted run regenerates only missing batches. Spot-check by hand AAPL, AMZN, GOOGL, MSFT, BRK-B, GE and CRWD (or another cybersecurity pure play in the universe if CRWD is absent); results go into the PR description.

- [ ] **Step 1: Write the failing tests**:
  - `test_committed_profiles_load`: `load_profiles(_ROOT / COMPANY_PROFILES_PATH, _ROOT / INDUSTRY_TAGS_PATH)` returns ≥ 1 profile.
  - `test_every_universe_ticker_has_a_profile`: tickers read from `universe_default.csv` (skip `#` lines and the `ticker` header) minus `PROFILE_EXCEPTIONS: frozenset[str]` (defined in the test module; the spec allows an exception only "if a 10-K is unavailable", so each entry carries a comment naming the missing filing, and the PR description lists them) `<=` profile keys; and `PROFILE_EXCEPTIONS` ∩ profile keys is empty; and every profile key is in the universe.
  - `test_cybersecurity_search_finds_pure_plays_not_sidelines`: the `cybersecurity` tag is on `CRWD`, `PANW` and `FTNT` and on neither `MSFT` nor `CSCO` (spec §5 names Microsoft and Cisco; all five are in the universe and must have profiles).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Generate** the profiles in batches as described.
- [ ] **Step 4: Run** the tests — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#333): company profiles for the default universe`.

### Task 4: Detail page shows description and tags

**Files:**
- Modify: `src/bot/web/views.py`, `src/bot/web/site.py`, `src/bot/web/templates/detail.html`, `src/bot/web/static/app.css` (only if spacing needs it)
- Test: `tests/unit/test_web_views.py`, `tests/unit/test_web_site.py`

**Interfaces:**
- Consumes: `CompanyProfile`, `ProfileTag` (Task 1).
- Produces:
  - in `views.py`: `SOURCE_WORDS: dict[str, str] = {"segment": "reported segment", "disaggregation": "revenue disaggregation", "judgment": "estimated from the 10-K"}`
  - `@dataclass(frozen=True) class TagView: label: str; tooltip: str`
  - `@dataclass(frozen=True) class ProfileView: description: str; tags: tuple[TagView, ...]`
  - `def profile_view(profile: CompanyProfile | None) -> ProfileView | None`
  - `DetailView.profile: ProfileView | None = None`; `detail_view(entry, ref, profile: CompanyProfile | None = None)`
  - `build(reports_dir: Path, out_dir: Path, base_url: str, profiles: Mapping[str, CompanyProfile] | None = None) -> int`

Tooltip = tag description, a space, then `f"~{share:.0%} of revenue, {SOURCE_WORDS[source]}, FY{fiscal_year}."` (e.g. "Endpoint and cloud security software. ~95% of revenue, reported segment, FY2026.").

- [ ] **Step 1: Write the failing tests**:
  - views: `test_profile_view_words_the_share_and_source` → tooltip ends with `"~95% of revenue, reported segment, FY2026."`; judgment → `"estimated from the 10-K"`; tags keep descending share order; `profile_view(None) is None`.
  - site: `test_detail_shows_profile_under_the_heading`: build with `profiles={"AAA": ...}` → `c/AAA.html` and `f/AAA.html` contain `class="profile"`, the description, and a `badge` with `<abbr title="...~95% of revenue, reported segment, FY2026.">Cybersecurity</abbr>`; the profile block's index is after `</h1>` and before `class="instrument"`.
  - `test_detail_without_profile_has_no_profile_block`: BBB (no profile) page lacks `class="profile"`; `build(..., profiles=None)` works.
  - `test_profile_text_is_escaped`: description `"AT&T <b>"` renders `AT&amp;T &lt;b&gt;`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement**: `site.build` passes `profiles.get(ticker)` to `detail_view` (in `_renderable`, `list_page`, `_write_company`); `detail.html` renders, inside `<header class="detail-head">` right after `<h1>`, `<div class="profile"><p class="profile-desc">…</p><ul class="profile-tags" aria-label="Industries">` with `<li class="badge badge-outline">{{ term(t.label, t.tooltip) }}</li>` per tag (only if `detail.profile`). `badge-outline` is present in the precompiled `daisyui.css`; add a test in `tests/unit/test_web_theme.py` style asserting it, so a theme rebuild that drops it fails.
- [ ] **Step 4: Run** the web tests — Expected: PASS (existing ones unchanged).
- [ ] **Step 5: Commit** `feat(#333): detail page shows the company profile`.

### Task 5: Search matches tags

**Files:**
- Modify: `src/bot/web/views.py`, `src/bot/web/site.py`, `src/bot/web/templates/_rows.html`, `src/bot/web/templates/_controls.html`, `src/bot/web/static/viewer.js`, `docs/DESIGN.md` (Search component line)
- Test: `tests/unit/test_web_views.py`, `tests/unit/test_web_site.py`, `tests/unit/test_web_viewer_js.py`

**Interfaces:**
- Consumes: `CompanyProfile` (Task 1), `build(..., profiles=...)` (Task 4).
- Produces: `RowView.tags: str = ""`; `def search_tags(profile: CompanyProfile | None) -> str` — slugs and labels, lower-cased, joined with `" "`, `""` for no profile; `row_view(ref, profile: CompanyProfile | None = None)`.

- [ ] **Step 1: Write the failing tests**:
  - views: `search_tags(profile)` for cybersecurity → `"cybersecurity cybersecurity"`-style contents containing both slug and lower-cased label; `search_tags(None) == ""`.
  - site: a row with a profile carries `data-tags="…cybersecurity…"` on its `<tr>`; a row without one has no `data-tags`; the tags are not printed in any `<td>`; the search box reads `Search by ticker, name or industry` and placeholder `Ticker, name or industry`. Update `test_search_box_sits_between_filter_and_count`'s label assertion.
  - js: `test_search_matches_tags`, in the style of the existing source-text tests in `test_web_viewer_js.py`: inside the `applySearch` body, `row.getAttribute("data-tags")` is read, lower-case `indexOf(q)` is applied to it, and the hide condition is `!!q && !inTicker && !inName && !inTags`. Keep `test_search_matches_each_cell_separately` green (no concatenation). Behaviour is checked in a browser in stage 4.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement**: `_rows.html` adds `{% if r.tags %} data-tags="{{ r.tags }}"{% endif %}` to `<tr>`; `applySearch` adds `var inTags = (row.getAttribute("data-tags") || "").indexOf(q) !== -1;` and hides when none of ticker/name/tags match; `_controls.html` label and placeholder; `site.build` passes the profile to `row_view`; DESIGN.md Search line mentions industry tags.
- [ ] **Step 4: Run** the web tests and `node --check` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#333): search matches industry tags`.

### Task 6: `bot site` reads the committed profiles; docs

**Files:**
- Modify: `src/bot/cli.py` (`site`), `CONTEXT.md` (domain terms), `docs/adr/0008-read-only-web-viewer.md` (inputs line), `docs/plano/*` only if `python3 docs/plano/build.py` fails
- Test: `tests/unit/test_cli_site.py`

**Interfaces:**
- Consumes: `load_profiles`, `COMPANY_PROFILES_PATH`, `INDUSTRY_TAGS_PATH`, `ProfileError` (Task 1); `build(..., profiles=...)` (Task 4).

Options `--profiles PATH` (default `config/company_profiles.yaml`) and `--industry-tags PATH` (default `config/industry_tags.yaml`). The CLI checks `path.exists()` on both before calling the loader. Both absent → warn on stderr ("no company profiles: … not found") and build without profiles. One present and the other absent, or either invalid → `ERROR: …`, exit 2. No `Settings` load (the bare-env fixture must keep passing).

- [ ] **Step 1: Write the failing tests**: `test_site_shows_profiles_from_config` (tmp yaml files passed via the options → `c/AAA.html` contains the description); `test_site_without_profile_files_still_builds` (both paths missing → exit 0); `test_site_rejects_an_invalid_profile_file` (unknown tag → exit 2, message contains `unknown tag`); `test_site_rejects_a_lone_profile_file` (only `--industry-tags` present → exit 2).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** the options; add **Company profile** and **Industry tag** to CONTEXT.md's domain language (≥10% rule, source kinds, display and search only); ADR 0008's "Source of data" bullet mentions the two config files; run `python3 docs/plano/build.py`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py` and fix only what they flag.
- [ ] **Step 4: Run** the full suite, ruff and mypy — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#333): bot site reads the company profiles`.

## Assumptions

Decided during plan grilling (no written source; any choice satisfies the issue). Rejected alternative in brackets.

- Words for `disaggregation` in the tooltip: "revenue disaggregation" (spec gives words only for `segment` and `judgment`). [the raw identifier]
- Shares sum checked on the recorded two-decimal values with a 1e-9 tolerance; exactly 1.00 passes. [checking unrounded shares, which the file does not hold]
- Synonym tags are prevented by review, not by a test: the spec has the user review the vocabulary in the PR (§6.1). Task 3 may add a tag only for coverage. [a synonym blocklist test]
- JS search is tested by source-text assertions like the existing viewer tests, plus the stage-4 browser script. [a node DOM harness, which the repo has no precedent or dependency for]
- `bot site` with only one of the two files present fails (exit 2); with both absent it warns and builds without profiles. [silently ignoring a lone file]
- Accession/ticker mapping verified by a scratch check against EDGAR `submissions` before commit, plus the seven hand spot-checks. [trusting the generator]
- ADR 0008 gets a line under "Source of data" rather than a new ADR: the decision (site is a pure function of committed files) does not change; the ADR was amended in place before (its "Visual system" consequence). [a new ADR]

## Grilling

- Rounds: 1 (revisions were clarifications and added tests, not a new seam; no second round).
- Questions: 18. Sources: ISSUE/spec 7, CODE 7, DOC 2, NO SOURCE → technical assumption 7 (some questions cited and also produced an assumption).
- Spec ambiguities: none. Follow-up issues opened: none.
- Griller model: fable.
