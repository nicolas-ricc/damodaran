# Refresh board (#146) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw `docs/pipeline/refresh.d2`, the board that shows how `bot refresh` turns downloads into DuckDB rows (Damodaran, SEC EDGAR fundamentals, end-of-day prices, foreign exchange), have CI render it to `refresh.svg`, and link it from `pipeline.d2`.

**Architecture:** One new d2 board that pulls the shared classes with `...@classes`; four top-level containers (`damodaran`, `fundamentals`, `prices`, `fx`) holding `step` / `decision` nodes and their notes, plus top-level entry points, external services, repo files and a `duckdb` container with the nine tables. Every name taken from the code is cited with a `@symbol` / `@table` / `@file` / `@const` directive in a d2 line comment. Tests in `tests/unit/test_pipeline_diagram.py` pin the required citations, the node keys and classes, the formulas and the gap notes. Rendering happens only in the `pipeline-diagram` workflow (no d2 locally).

**Tech Stack:** d2 v0.9.0 + TALA (CI only), Python 3 / pytest, `docs/pipeline/check.py` (stdlib).

**Spec:** GitHub issue #146 (child of story #144); inherited decisions in its "Inherited decisions" section. `docs/pipeline/README.md` documents the directive syntax.

## Global Constraints

- Board file: `docs/pipeline/refresh.d2`; first non-blank line `...@classes`; imports no other board; `class:` is a node's first attribute.
- Only the nine classes in `classes.d2`: `step`, `decision`, `store`, `external`, `file`, `output`, `cron`, `note`, `gap`. No new shapes, no styles.
- A note is a child of the node it annotates, with a markdown block label `|md ... |`. A `gap` note's text starts with `Gap:`.
- English; domain words exactly as in `CONTEXT.md` (universe, sector benchmark, fiscal year, listing / reporting / valuation currency, ...).
- Formulas in plain math with Unicode operators (`×`, `÷`, `−`), never function names.
- Every acronym is expanded the first time it appears in the board (same line or earlier); every acronym used is a key of `_ACRONYMS`.
- Directives live in `#` comments, trailing the line whose visible text they check, never inside `|md ... |`; a `@const` value must be visible on that same line. No `@` at the start of a word anywhere else (visible text included).
- An `#` inside a label only inside double quotes (an unquoted ` #` starts a comment).
- Every edge carries a label.
- Do not touch `src/`. Do not hand-write or hand-edit any SVG or `rendered.sha256`.
- Quality bar: `uv run ruff check . && uv run mypy src && uv run pytest -q` green, and the `pipeline-diagram` workflow green on the head commit.
- Commits: `docs(#144): ...` for board work (story convention), `test(#146)` / `fix(#146)` / `chore(#146)` for pipeline stages.

## Layout rules (from the overview render)

The overview rendered 15,502 px wide because d2 does not wrap a single-line label. On this board:
- A node or edge label line is at most ~70 characters. A longer label is broken with `\n` inside its double quotes (d2 renders it as a line break); never put an acronym directly after `\n` (the acronym test needs a word boundary): write a lower-case word first or rephrase.
- Longer content goes into a `note` child as a markdown list (`- item` per line): each item renders on its own line.
- A `@const` directive sits on a label line (a decision or a step label), not on a multi-line note. Directive arguments are always fully qualified (`bot.ingest.sec_edgar._SHARE_SCALE_FACTORS`, never a bare name).
- `gap` notes are single-line `|md Gap: ... |` blocks, as in `pipeline.d2`; multi-line markdown lists are for `note` class only.
- Every `step` and `decision` cites, with `@symbol`, the function that implements its rule (module constants are not symbols: cite them with `@const`).

## Review Focus

1. **A cited constant drifting from its label.** `@const` makes pytest fail when e.g. `_FRESH_DAYS` changes and the label still says 7; covered by `test_every_directive_is_valid` (existing).
2. **An acronym slipping in unexpanded** (EBIT, EBITDA, SIC, ADR are new here); covered by `test_acronyms_are_expanded` (existing) plus the new `_ACRONYMS` entries in Task 1.
3. **A d2 syntax error that only CI sees** (no local d2). Mitigation: copy syntax only from `pipeline.d2`, which renders; Task 4 reads `--log-failed`.
4. **A label claiming something the code does not do** (e.g. FX converting rates under the default provider). Covered by the formula/rule substring tests and the gap-note tests (Task 1–3), and by the code review stage.
5. **Unlabelled edges on the new board.** The existing `test_every_edge_is_labelled` only checks the overview; Task 1 extends it to every board.

---

## Node map (all tasks use these exact keys)

Top level:
- `weekly` (cron) `# @file scripts/weekly.sh`, `daily` (cron) `# @file scripts/daily.sh`, `price_fill` (cron) `# @file scripts/price_fill.sh`.
- `cli` (step, label starts `bot refresh`) `# @symbol bot.cli.refresh`; `region` (decision `@symbol bot.cli.refresh`: Damodaran requested with `--region` other than US → whole command refused before any source runs, exit code 2).
- Externals: `damodaran_data`, `edgar`, `tiingo`, `stooq`, `fmp` (class `external`). `stooq` cites `@symbol bot.ingest.stooq`, `tiingo` cites `@symbol bot.ingest.edgar_tiingo`, `fmp` cites `@symbol bot.ingest.fmp`.
- Files: `universe_csv` `# @file src/bot/ingest/universe_default.csv`, `industry_mapping_csv` `# @file src/bot/ingest/industry_mapping.csv` (class `file`).
- `duckdb` container with one `store` child per table, each on its own line with `# @table <name>`: `damodaran_industry`, `damodaran_country`, `companies`, `financials_annual`, `financials_quarterly`, `filings_log`, `prices_daily`, `currencies`, `refresh_log`.

`damodaran` container:
- `download` (step) `@symbol bot.ingest.damodaran.import_damodaran`; note `download.files` listing the 8 files (wacc.xls first, margin, capex, pedata, pbvdata, vebitda, psdata, ctryprem.xls) and their columns.
- `files_ok` (decision `@symbol bot.ingest.damodaran.import_damodaran`): wacc.xls or ctryprem.xls fails → error run, nothing written; any other file fails → run continues as `partial` without its columns.
- `merge` (step) `@symbol bot.ingest.damodaran.merge_industry_datasets`: outer join on industry name; an earlier file wins a shared column.
- `derive` (step) `@symbol bot.ingest.damodaran.derive_industry_columns`: `D/E = w ÷ (1 − w)` with `w = D/(D+E)` (left empty when w = 1); `beta_unlevered = beta_levered ÷ (1 + (1 − tax) × D/E)`.
- `country` (step) `@symbol bot.ingest.damodaran.parse_country_tax_rates` and `@symbol bot.ingest.damodaran.parse_preheader_scalar`: sheet "ERPs by country", parsing stops at the second (unrated) table; tax rate from sheet "Country Tax Rates", kept only within [0, 1]; risk-free rate from the wacc.xls cell "Long Term Treasury bond rate =".
- `empty_rows` (decision `@symbol bot.ingest.damodaran._import_files_into_run`): no industry rows or no country rows → `partial`.
- `write` (step `@symbol bot.ingest.damodaran.upsert_industry_rows`, `@symbol bot.ingest.damodaran.upsert_country_rows`): replace the `(region, year)` rows of `damodaran_industry` and the `year` rows of `damodaran_country`; region = `--region`, year = `--year` or the current year; one `refresh_log` row (source damodaran).
- Gap `write.us_only`: `Gap: only the US Damodaran dataset is ingested ...` citing ADR 0005 not implemented (`# @file docs/adr/0005-currency-handling-and-valuation-currency.md` on the line).
- Gap `country.risk_free`: `Gap: the US risk-free rate is written into every country row ...` (ADR 0005's per-currency rate not implemented).

`fundamentals` container:
- `mapping` (step) `@symbol bot.ingest.industry_mapping.load_industry_mapping`: provider industry label (EDGAR: Standard Industrial Classification (SIC) description) → `companies.industry_damodaran`; note: unmapped label → empty column, sector rules skip later; missing file → empty mapping.
- `mapping_valid` (decision) `@symbol bot.reference.industries`: a target outside the Damodaran industry list fails the load; duplicate rows fail too.
- `skip` (decision) `@symbol bot.ingest.universe._should_skip`: provider's latest 10-K/10-Q filing date not after the newest `filings_log` date → skipped, no import; `--force` bypasses; probe error → import anyway.
- `import` (step) `@symbol bot.ingest.universe.refresh_universe` and `@symbol bot.ingest.universe.import_company`: one transaction per ticker writing `companies`, `financials_annual`, `financials_quarterly`, `filings_log`; note names `EdgarPricedProvider` (`@symbol bot.ingest.edgar_base.EdgarPricedProvider` on its line) and that source is restamped as the provider name so the skip watermark matches.
- `periods` (decision) `@symbol bot.ingest.sec_edgar._collect_period_rows`, `@const bot.ingest.sec_edgar.ANNUAL_SPAN_DAYS`, `@const bot.ingest.sec_edgar.QUARTERLY_SPAN_DAYS`: annual row only for a duration fact of 350–380 days from a 10-K or 10-K/A; quarterly 80–100 days from a 10-Q or 10-Q/A.
- `fiscal` (step) `@symbol bot.ingest.sec_edgar.parse_company_facts`, `@symbol bot.ingest.sec_edgar._fiscal_quarter_key`: fiscal year = calendar year of the period end (never the filing's `fy`/`fp`); quarter numbered from the nearest annual end; two rows on one label → the later end kept.
- `precedence` (decision `@symbol bot.ingest.sec_edgar._collect_period_rows`): per column and period end, the first concept in the list with an accepted fact wins; note gives one example (revenue: Revenues, then RevenueFromContractWithCustomerExcludingAssessedTax, ...).
- `derive` (step) `@symbol bot.ingest.sec_edgar._derive_financial_fields`: `EBITDA = EBIT + depreciation`, `free cash flow = operating cash flow − capex`, `working capital = current assets − current liabilities`, only when not reported. EBIT and EBITDA expanded at first use.
- `shares` (decision) `@symbol bot.ingest.sec_edgar._rescale_shares_diluted` with `@const bot.ingest.sec_edgar._SHARE_SCALE_FACTORS`, `@const bot.ingest.sec_edgar._MIN_SHARE_COMPARATORS`, `@const bot.ingest.sec_edgar._SHARE_SCALE_TOLERANCE` (label broken with `\n`): diluted share count × 1,000,000 or × 1,000 when median(other annual counts) ÷ count lies within factor ÷ 2 … factor × 2; needs at least 3 other counts.
- `status` (decision) `@const bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE`, `@const bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE`: failure rate = failed ÷ attempted; at most 5% → success, at most 25% → partial, else error; not success → exit code 2.
- `rate_limit` (decision `@symbol bot.ingest.universe._run_bulk_refresh`): provider rate limit → this and every remaining ticker deferred, not failed; failure rate counts attempted tickers only.
- `edgar -> fundamentals.import` carries "company facts, submissions"; `SecEdgarClient.shares_outstanding` is cited on the prices board part (see below).

`prices` container:
- `only_missing` (decision `@symbol bot.ingest.universe.refresh_prices`): `--only-missing` → only tickers with no stored price.
- `up_to_date` (decision `@symbol bot.ingest.universe._last_weekday_before`): newest bar on or after the last weekday before today → skipped, no request.
- `order` (step) `@symbol bot.ingest.universe.refresh_prices`, `@symbol bot.ingest.universe._stale_first`: never priced first, then oldest newest bar first.
- `fetch` (step `@symbol bot.ingest.universe._refresh_one_price`, note line `@symbol bot.ingest.tiingo.TiingoClient.daily_prices`): bars after `max(date)` stored for the ticker (incremental); currency from `companies.currency`; note: Tiingo is the default source (status 429 → rate limit), Stooq the alternative read from `BOT_STOOQ_DIR` CSVs, FMP the optional provider (`BOT_DATA_PROVIDER=fmp`).
- Gap `fetch.default_provider`: `Gap: docs/plano/estado.py still calls edgar-stooq the default provider; the code default is edgar-tiingo` (`# @file docs/plano/estado.py`).
- `market_cap` (decision) `@const bot.ingest.edgar_base._FRESH_DAYS`, `@symbol bot.ingest.sec_edgar.SecEdgarClient.shares_outstanding` (separate line allowed): `market cap = close × shares outstanding`, newest bar only, only when at most 7 days old; shares = newest SEC EDGAR dei EntityCommonStockSharesOutstanding.
- `rate_limit` (decision `@symbol bot.ingest.universe._run_bulk_refresh`): rate limit → remaining tickers deferred; the run prints "tickers deferred" and `daily.sh` runs another round.
- `status` (decision): same thresholds as fundamentals, cited again with both `@const` directives so the numbers on this label are pinned too.

`fx` container:
- `currencies` (step) `@symbol bot.ingest.universe.refresh_fx`: distinct non-USD currencies in `companies`.
- `fetch` (step) `@symbol bot.utils.fx.import_fx_rates`: daily rate per currency into `currencies`; note: `usd = amount × rate_to_usd`, nearest prior date (never forward) when later read.
- Gap `fetch.no_op`: `Gap: under the default provider (SEC EDGAR with Tiingo or Stooq) FX returns no rates ...` — only FMP supplies them.

Edges (all labelled): cron → `cli` with the command each runs (`weekly`: `bot refresh --all`; `daily`: `bot refresh --prices` in rounds until no "tickers deferred" (at most `BOT_PRICE_ROUNDS`, default 10, `BOT_PRICE_RETRY_PAUSE` s apart, default 3600), then `bot refresh --fx`; `price_fill`: hourly `bot refresh --prices --only-missing` until every company has a price); `cli -> region`, `region -> damodaran.download`; `cli` → each other container in order (labels numbered `1.`…`4.`: damodaran, fundamentals, prices, FX); externals and files into the steps that read them; steps into the stores they write; `duckdb.companies -> prices.fetch` ("listing currency") and `duckdb.companies -> fx.currencies`; `duckdb.filings_log -> fundamentals.skip` ("newest filing date"); `duckdb.prices_daily -> prices.up_to_date` ("newest bar per ticker"); each container's status/outcome into `duckdb.refresh_log`.

---

### Task 1: Tests, acronyms and the Damodaran flow with entry points

**Files:**
- Create: `docs/pipeline/refresh.d2`
- Modify: `tests/unit/test_pipeline_diagram.py`

**Interfaces:**
- Consumes: `_check()`, `_boards()`, `_block()`, `_node_class()` in the test file; `check.normalize`, `check.visible`.
- Produces: helper `_refresh() -> str` (`_boards()["refresh"]`), `_REFRESH_NODES: list[tuple[str, str]]`, `_REFRESH_TEXT: dict[str, list[str]]` (node key → substrings its block must contain after `normalize`), used by Tasks 2–3.

- [ ] **Step 1: Write the failing tests** (stage 3 commits them all at once; listed here for ownership)
  - Add `"refresh"` entries to `_REQUIRED_SYMBOLS` (the 25 symbols of the issue), `_REQUIRED_TABLES` (the 9 tables), `_REQUIRED_FILES` (the 5 files), `_REQUIRED_CONSTS` (the 8 constants).
  - Add to `_ACRONYMS`: `"EBIT": "earnings before interest and taxes"`, `"EBITDA": "earnings before interest, taxes, depreciation and amortization"`, `"SIC": "Standard Industrial Classification"`, `"ADR": "architecture decision record"`.
  - `test_refresh_nodes(key, cls)` parametrized over `_REFRESH_NODES` (every key of the node map with its class; gap notes `gap`, plain notes `note`): `assert _node_class(_refresh(), key) == cls`.
  - `test_refresh_containers_hold_steps_and_decisions`: for each of `damodaran`, `fundamentals`, `prices`, `fx`, its block contains `class: step`; for the first three also `class: decision`.
  - `test_refresh_text(key)` parametrized over `_REFRESH_TEXT`: each substring in `normalize(_block(...))`. Entries: `damodaran.derive`: `D/E = w ÷ (1 - w)`, `w = D/(D+E)`, `beta_unlevered = beta_levered ÷ (1 + (1 - tax) × D/E)`; `damodaran.merge`: `outer join`, `earlier file wins`; `damodaran.files_ok`: `wacc.xls`, `ctryprem.xls`, `partial`, `error`; `region`: `US`, `exit code 2`; `fundamentals.derive`: `EBITDA = EBIT + depreciation`, `free cash flow = operating cash flow - capex`, `working capital = current assets - current liabilities`; `fundamentals.shares`: `median`, `factor ÷ 2`, `factor × 2`; `fundamentals.periods`: `10-K`, `10-Q`; `fundamentals.fiscal`: `calendar year of the period end`; `fundamentals.skip`: `--force`; `fundamentals.status`: `failed ÷ attempted`; `fundamentals.rate_limit`: `deferred`; `prices.order`: `never priced first`; `prices.up_to_date`: `last weekday before today`; `prices.market_cap`: `market cap = close × shares outstanding`; `prices.only_missing`: `--only-missing`; `fx.fetch`: `usd = amount × rate_to_usd`, `nearest prior`.
  - `test_refresh_gap_notes`: `damodaran.write.us_only` contains `ADR 0005`; `fx.fetch.no_op` contains `Financial Modeling Prep`; `damodaran.country.risk_free` contains `risk-free`.
  - `test_gap_notes_start_with_gap` (every board): every node line containing `class: gap` has visible text matching `\|md\s+Gap:`.
  - Change `test_every_edge_is_labelled` to loop over every board in `_boards()` (report `stem: line`).
  - `test_pipeline_links_the_refresh_board`: `_block(_overview(), "refresh")` contains `link: refresh.svg`.
  - `test_refresh_daily_defaults_match_script`: `scripts/daily.sh` contains `BOT_PRICE_ROUNDS:-10` and `BOT_PRICE_RETRY_PAUSE:-3600`, and the board's `daily -> cli` edge line shows `10` and `3600`.
  - `test_estado_default_provider_gap_is_current`: the gap `prices.fetch.default_provider` exists exactly while `docs/plano/estado.py` contains `BOT_DATA_PROVIDER=edgar-stooq)` and `bot.config.Settings.model_fields["data_provider"].default == "edgar-tiingo"`; when estado is fixed the test fails and says to remove the gap.
  - `test_refresh_cron_edges`: `weekly -> cli`, `daily -> cli`, `price_fill -> cli` edges exist; the `daily` one's visible line contains `tickers deferred`.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py` — Expected: the new tests FAIL (no `refresh.d2`).

- [ ] **Step 3: Write** `refresh.d2` with `...@classes`, `direction: down`, the top-level nodes, `duckdb` container, and the full `damodaran` container per the node map, with edges.

- [ ] **Step 4: Run** `python3 docs/pipeline/check.py` — Expected: only `refresh.d2 has no refresh.svg` and `rendered.sha256 is stale` (both fixed by Task 4). `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "refresh and (damodaran or region or cron) or acronyms or every_directive or gap_notes or edge"` — Expected: PASS.

- [ ] **Step 5: Commit** the board only: `docs(#144): refresh board — entry points and Damodaran flow` (the tests were already committed by stage 3 as `test(#146): evals`).

### Task 2: Fundamentals flow

**Files:** Modify `docs/pipeline/refresh.d2`.

**Interfaces:** Consumes Task 1's node map, `_REFRESH_NODES`, `_REFRESH_TEXT`.

- [ ] **Step 1:** Tests already in place (Task 1). Run `uv run pytest -q tests/unit/test_pipeline_diagram.py -k fundamentals` — Expected: FAIL.
- [ ] **Step 2:** Add the `fundamentals` container per the node map, with edges from `edgar`, `fmp`, `universe_csv`, `industry_mapping_csv`, from/to the stores.
- [ ] **Step 3:** Run the same `-k fundamentals` selection plus `test_every_directive_is_valid` and `test_acronyms_are_expanded` — Expected: PASS.
- [ ] **Step 4: Commit** `docs(#144): refresh board — fundamentals flow`.

### Task 3: Prices and FX flows, pipeline link

**Files:** Modify `docs/pipeline/refresh.d2`, `docs/pipeline/pipeline.d2` (add `link: refresh.svg` as the `refresh` node's second attribute, after `class: step`).

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "prices or fx or link"` — Expected: FAIL.
- [ ] **Step 2:** Add `prices` and `fx` containers and the link.
- [ ] **Step 3:** Run the whole file: every test PASS except `test_check_py_exits_zero` and `test_each_board_has_a_rendered_svg` (no SVG yet). `test_required_citations_present` PASS for every kind.
- [ ] **Step 4: Commit** `docs(#144): refresh board — prices and FX flows, linked from the overview`.

### Task 4: Render through CI and commit the render (controller, needs push)

- [ ] Push the branch; find the `pipeline-diagram` run whose `headSha` equals `git rev-parse HEAD`; `gh run watch <id> --exit-status`.
- [ ] On a build failure, `gh run view <id> --log-failed`, fix the `.d2` line d2 names, push again.
- [ ] When the build step is green: `gh run download <id> -n pipeline-render -D /tmp/render`; copy `*.svg` and `rendered.sha256` into `docs/pipeline/`; look at `/tmp/render/refresh.png`; fix layout problems in the source (and re-render) if a node is unreadable; commit `docs(#144): render refresh, pipeline`; push; the run on that commit must be fully green.
- [ ] `python3 docs/pipeline/check.py` exits 0; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Manual verification (goes in the PR)

- Open `refresh.svg`; pick three thresholds at random and confirm them against the code lines (the `@const` tests already pin the eight cited constants).
- A reader can answer the four questions for each step (purpose, inputs/outputs, math, decisions) from the board alone.

## Assumptions

- **Stores in one top-level `duckdb` container**, not one copy per sub-flow container: `refresh_log` and `companies` are touched by several flows and the overview test pins "each table on its own node". Rejected: duplicating store nodes per container.
- **Long labels break with `\n`** inside double quotes. Rejected: markdown notes for every long label (directives cannot sit inside `|md` blocks, so cited values must be on label lines).
- **Every step/decision cites its implementing function** with `@symbol`, beyond the issue's required list, so the code reviewer has a pointer for each claim. Rejected: citations only where the issue requires them.
- **Two extra tests** pin values not reachable by `@const`: the `daily.sh` defaults (10 rounds, 3600 s) and the staleness of the `estado.py` gap note. Rejected: leaving them unchecked.
- **Commit prefixes:** board work `docs(#144)` (issue: "Commits: Conventional Commits, `docs(#144): ...`"), pipeline-stage commits `test(#146)` / `fix(#146)` / `chore(#146)` (pipeline instructions).

## Grilling

- Rounds: 1 (the revisions add citations, two tests and a label-wrapping rule; no task or seam changed, so no second round).
- Questions: 18. Sources: ISSUE 4 (Q1 required `@file` list has 5 entries, extra citations allowed; Q11 "The staleness step is expected to fail on a push whose SVGs are not yet committed"; Q12 copy `*.svg` and `rendered.sha256` from the same artifact; Q13 `docs(#144)` commits), CODE 10 (Q2 `check.py` `renderings`/`shown`: 0.05 → `5%`, tuples need every element; Q3 `test_pipeline_diagram.py` `_resolve` needs the dotted module path; Q4 `check.py` `normalize` maps U+2212 to `-` only; Q5 `_block` searches each part inside the previous block; Q6 `_ACRONYMS` holds SEC, EDGAR, FX, FMP, WACC, EOD and `_ACRONYMS_EXEMPT` holds US, USD, CSV; `_ACRONYM_RE` needs two capitals with word boundaries, so `10-K`, `D/E`, `ERPs` never match; Q9 per-function citations added; Q10 `cli.py:174-195`; Q14 `pipeline.d2` `refresh` node has `class: step` first, the import test only reads `@word` in visible text; Q17 `pipeline.d2` `fx_gap` is a single-line md gap; Q18 `check.py` `_scan` keeps quoted text and md content, drops only the comment), NO SOURCE 3 (Q7, Q8, Q16: technical assumptions above), out of scope 1 (Q15 → #154).
- Corrections made: bare `@const` names fully qualified; `region` decision text (the whole command is refused, `cli.py:174-181`); `prices.status` cites both thresholds; label-wrapping rule for edges and long decisions.
- Issues opened: #154 (concurrent DuckDB writers between `daily.sh` and `price_fill.sh`).
- Result: ok.
