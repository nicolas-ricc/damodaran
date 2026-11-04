# Margin of safety on a price in the valuation currency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the newest close from its listing currency into the valuation currency, with the `currencies` FX rates, before every price-based figure (margin of safety, verdict, sensitivity grid, market P/E, holding marks): the "one FX conversion" of ADR 0005 *Consequences*.

**Architecture:** One pure helper, `bot.utils.fx.convert_price`, holds the rule `close × rate_listing ÷ rate_valuation` and its guards; `bot.portfolio.sync._market_value` delegates to it. The valuator's loaders (`load_valuation_input`, `bulk_load_valuation_inputs`) read the newest close with its currency and date, plus the two rates on or before that date, into `ValuationInput`, and log `analysis.price_fx_missing` once per pair. `analyze` converts with the helper; `Analysis.current_price` becomes the converted price, so the margin of safety, grid, sanity check, report, sidecar, marks and screener second pass all read it unchanged.

**Tech Stack:** Python 3.12 (dataclasses, `type` aliases), DuckDB 1.5 (`ASOF LEFT JOIN`), Jinja2, pytest, structlog `capture_logs`, d2 v0.9.0 and TLC (both in CI only).

**Spec:** issue #222 and its "Agent Brief" comment (the maintainer's decision: convert with FX, do not refuse the margin of safety).

## Global Constraints

- Conversion rule, identical to `bot.portfolio.sync._market_value`: listing currency = valuation currency (case-insensitive), or either one NULL → the close as is, `fx_rate` None. Otherwise `price = close × rate_to_usd(listing) ÷ rate_to_usd(valuation)`, each rate the nearest on or before the close's date (`get_fx_rate` semantics; USD = 1.0). A missing or non-positive rate → price `None`.
- Price `None` ⇒ `margin_of_safety` None, verdict `n/a`, grid cells keep intrinsic values with no margins, `sanity_check.market_pe` None.
- Warning event name: `analysis.price_fx_missing`, once per (listing, valuation) pair per run via the run-scoped `warned` set.
- No second copy of the rule: `sync._market_value` and the valuator both call `convert_price`.
- `bulk_load_valuation_inputs` keeps a constant number of queries (same count for 1 ticker and for many, mixed USD/EUR).
- Sidecar `SCHEMA_VERSION` stays `1` (additive keys).
- USD company, USD close: every output unchanged; `tests/fixtures/screener/second_pass_shortlist.golden` and the isolation `.md` goldens are not touched; `fx_rate` None.
- Out of scope: retiring `companies.currency` (ADR 0005 §1), converting financials/cash flows, forward FX, the snapshot-date bound on the mark's price (#225), mid-series reporting-currency changes.
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` pass. TLC runs in CI (`pipeline-diagram` / `models`).
- Never edit an SVG or `docs/pipeline/rendered.sha256` by hand: d2 is not on `PATH` here; the render comes from the `pipeline-render` artifact of the `pipeline-diagram` workflow after a push (as in #219).

## Decisions taken here

1. **Helper shape** (in `src/bot/utils/fx.py`):
   - `type FxLookup = Callable[[str], float | None]` moves here from `sync.py`; `sync.py` imports it (name stays importable from `bot.portfolio.sync`).
   - `@dataclass(frozen=True) class ConvertedPrice: price: float | None; fx_rate: float | None` — `fx_rate` is the cross rate `rate_listing / rate_valuation` applied, None when no conversion was needed or possible.
   - `def convert_price(close: float, listing_currency: str | None, valuation_currency: str | None, rate_to_usd: FxLookup) -> ConvertedPrice`. The price is computed as `close * rate_listing / rate_valuation` (this exact expression, as sync does today, so sync's floats do not move). The `close <= 0` guard stays in `_market_value` (it is a quote guard, not a conversion guard; the valuator already treats a price ≤ 0 as no margin).
2. **`ValuationInput` shape:** `current_price` is replaced by
   - `latest_close: LatestClose | None`, with `@dataclass(frozen=True) class LatestClose: close: float; currency: str | None; date: datetime.date` (public, in `analysis.py`, the newest non-null `prices_daily` row). `currency` is stored already normalised with `bot.reference.currencies.normalize_currency` (strip + upper, blank → None), the same function that normalises the valuation currency, so the "different" test, the USD shortcut and the rate keys all use one spelling. `convert_price` applies the same normalisation (it calls `normalize_currency`) before comparing and before calling `rate_to_usd`;
   - `close_rates: tuple[float | None, float | None] | None`: `(rate_to_usd(listing), rate_to_usd(valuation))` on or before `latest_close.date`, only when a conversion is needed (both currencies known and different); `None` otherwise. USD resolves to `1.0` without a query, as `get_fx_rate`.
   - The valuation currency is `assumption_inputs.valuation_currency` (already normalised, from the newest non-restated `financials_annual` row). No new read.
3. **One conversion function for both loaders and `analyze`:** `def price_in_valuation_currency(inputs: ValuationInput) -> ConvertedPrice` (module-level in `analysis.py`) calls `convert_price` with `{listing: r1, valuation: r2}.get`-style lookup over `close_rates`. `latest_close is None` → `ConvertedPrice(None, None)`.
4. **Bulk FX read:** one extra query, always issued when `kept` is non-empty (so the count does not depend on the currency mix): `(currency, date)` pairs unnested from two parallel arrays, `ASOF LEFT JOIN currencies c ON c.currency = n.currency AND c.date <= n.date`. Pairs are upper-cased; USD is never sent. The per-ticker loader uses `get_fx_rate` twice (only when a conversion is needed).
5. **Warning:** logged by the loaders (they take `warned`; `analyze(company=...)` does not), when `price_in_valuation_currency(...)` has a close but no price. Key in the existing `warned: set[str | None]`: the string `f"price_fx:{listing}/{valuation}"` (cannot collide with a bare ISO code). Fields: `listing=<code>`, `valuation=<code>`, `date=<close date iso>`, `listing_rate=<rate or None>`, `valuation_rate=<rate or None>` (so a non-positive row is told apart from an absent one). With `warned=None` it logs on every call (same as `_warn_uncovered`). The bulk loader logs each missing pair once, sorted.
6. **`Analysis` new fields**, appended after `intrinsic_value_after_governance`, all defaulting to `None` (so existing direct constructions keep working): `valuation_currency: str | None`, `listing_price: float | None` (raw close), `price_currency: str | None` (listing currency), `fx_rate: float | None`, `price_date: datetime.date | None` (the close's date; the report's "rate date", rates are taken on or before it). `current_price` = the converted price.
7. **Report copy** (`templates/analysis.md.j2`):
   - Header: `currency {{ a.valuation_currency or "n/a" }}` — label word unchanged so USD goldens do not move.
   - After the `Current price` line, only when `a.fx_rate is not none`:
     `- **Price conversion:** close {{ a.listing_price | per_share }} {{ a.price_currency }} × {{ "%.6f" | format(a.fx_rate) }} = {{ a.current_price | per_share }} {{ a.valuation_currency }} (rates on or before {{ a.price_date }})`
   - Price `None` with `listing_price` present (rate missing): `- **Current price:** close {{ a.listing_price | per_share }} {{ a.price_currency }} has no exchange rate into {{ a.valuation_currency }} on or before {{ a.price_date }} — margin of safety cannot be computed.` The no-close line stays as is.
8. **Docs:** ADR 0005 status says the price conversion (the price half of §3 and the first *Consequences* bullet) is implemented by #222; §1 stays open. CONTEXT.md "Margin of safety" adds "with `current_price` the newest close converted into the valuation currency". Atlas: see Task 5.

## Review Focus

1. **A non-USD company whose rate series starts after the close date** (FX history fetched later than prices): price None, verdict `n/a`, one warning — not a crash and not the raw close. Test in Task 2 (`test_no_rate_on_or_before_close_date_gives_no_price`).
2. **Lower-case or padded currency codes in `prices_daily.currency`** (`"usd"` vs normalised `"USD"`): must compare equal and not trigger a conversion. Test in Task 1 (`test_convert_price_same_currency_any_case`).
3. **A listing currency of USD with a non-USD valuation currency** (the common ADR case: TWD reporter trading in USD): USD rate is 1.0 without a `currencies` row. Test in Task 1 (`test_convert_price_usd_needs_no_row`) and Task 2 (EUR case uses USD close).
4. **Many tickers sharing one missing pair in the screener's bulk load**: exactly one warning per pair, not one per ticker. Test in Task 2 (`test_bulk_loader_warns_once_per_missing_pair`).
5. **Sidecars from before #222 read by the site** (no `valuation_currency` key): the site reads only `current_price`; nothing new may index the new keys with `[...]`. Covered by the existing site tests; Task 3 adds no site code.

---

### Task 1: `convert_price` helper; `sync._market_value` delegates

**Files:**
- Modify: `src/bot/utils/fx.py`, `src/bot/portfolio/sync.py:36-38,114-131`
- Test: `tests/unit/test_fx.py` (new tests), `tests/unit/test_portfolio_sync.py` (must pass unchanged)

**Interfaces:**
- Produces: `FxLookup`, `ConvertedPrice(price, fx_rate)`, `convert_price(close, listing_currency, valuation_currency, rate_to_usd) -> ConvertedPrice` in `bot.utils.fx`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_fx.py`:
  - `test_convert_price_same_currency_any_case`: `convert_price(110.0, "usd", "USD", lambda c: None) == ConvertedPrice(110.0, None)`; also `" eur"`/`"EUR"` when the helper strips (it upper-cases and strips both codes before comparing).
  - `test_convert_price_unknown_currency_uses_close`: `convert_price(110.0, None, "EUR", rates)` and `(110.0, "USD", None, rates)` → `ConvertedPrice(110.0, None)`.
  - `test_convert_price_cross_rate`: rates `{"USD": 1.0, "EUR": 1.10}`; `convert_price(110.0, "USD", "EUR", rates.get)` → `price == pytest.approx(100.0)`, `fx_rate == pytest.approx(1 / 1.10)`.
  - `test_convert_price_usd_needs_no_row`: lookup that returns 1.0 for USD only via `get_fx_rate` on an empty `currencies` table plus an EUR row → converts.
  - `test_convert_price_missing_or_non_positive_rate`: parametrize EUR rate `None`, `0.0`, `-1.0` → `ConvertedPrice(None, None)`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_fx.py` — Expected: FAIL (ImportError `convert_price`).
- [ ] **Step 3: Implement** `convert_price` and `ConvertedPrice` in `bot/utils/fx.py` (Decision 1). Rewrite `_market_value` as: quote guard, then `convert_price(quote.close, quote.currency, pos.currency, fx)`, `None` if `.price is None`, else `pos.quantity * .price`. Move `FxLookup` to `fx.py` and import it in `sync.py`.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_fx.py tests/unit/test_portfolio_sync.py`, then the full suite `uv run pytest -q` — Expected: PASS, `test_portfolio_sync.py` not edited.
- [ ] **Step 5: Commit** `feat(#222): one price conversion helper shared with portfolio sync`.

### Task 2: Loaders read the close with its currency, date and rates

**Files:**
- Modify: `src/bot/valuator/analysis.py:260-268` (`_load_latest_price`), `:339-507` (`ValuationInput`, both loaders)
- Test: `tests/unit/test_valuation_bulk_load.py`, new `tests/unit/test_valuator_price_fx.py`

**Interfaces:**
- Consumes: Task 1 `convert_price`, `ConvertedPrice`.
- Produces: `LatestClose(close, currency, date)`, `ValuationInput.latest_close`, `ValuationInput.close_rates`, `price_in_valuation_currency(inputs: ValuationInput) -> ConvertedPrice`, warning `analysis.price_fx_missing`.

- [ ] **Step 1: Write the failing tests.**
  - In `test_valuation_bulk_load.py`: replace the two `.current_price` asserts with `bulk["NOPRICE"].latest_close is None` and `bulk["NULLCLOSE"].latest_close == LatestClose(8.0, "USD", date(2026, 5, 28))`. Add `test_bulk_and_per_ticker_match_for_mixed_usd_eur`: two extra tickers whose financials are `EUR` (one with an EUR rate on 2026-05-26, one whose EUR rate is only after the close), asserting bulk == per-ticker and `close_rates == (1.0, 1.10)` / `(1.0, None)`; and extend `test_bulk_valuation_inputs_query_count_is_constant` with the EUR tickers in `many`.
  - `test_bulk_loader_warns_once_per_missing_pair`: three EUR tickers with no EUR rate, `warned=set()` → exactly one `analysis.price_fx_missing` with `listing="USD", valuation="EUR"`.
  - In `test_valuator_price_fx.py`: `test_per_ticker_loader_warns_once_per_run` — two `load_valuation_input` calls sharing one `warned` set → one warning.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuation_bulk_load.py tests/unit/test_valuator_price_fx.py` — Expected: FAIL.
- [ ] **Step 3: Implement** Decisions 2–5. `_load_latest_price` becomes `_load_latest_close(conn, ticker) -> LatestClose | None` selecting `close, currency, date`. The bulk price query selects `ticker, close, currency, date`. Rates: Decision 4. In `analyze`, the line `current_price = inputs.current_price` becomes `current_price = price_in_valuation_currency(inputs).price`, so this commit is complete on its own (Task 3 adds the `Analysis` fields).
- [ ] **Step 4: Run** the same tests, then the full suite `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#222): valuation inputs carry the close, its currency, date and rates`.

### Task 3: `analyze` values against the converted price

**Files:**
- Modify: `src/bot/valuator/analysis.py:93-157` (`Analysis`), `:716`, `:803-900`
- Test: `tests/unit/test_valuator_price_fx.py`, `tests/unit/test_reporting_analysis_json.py`

**Interfaces:**
- Consumes: Task 2 `price_in_valuation_currency`.
- Produces: `Analysis.valuation_currency`, `.listing_price`, `.price_currency`, `.fx_rate`, `.price_date`; `Analysis.current_price` is converted.

- [ ] **Step 1: Write the failing tests** in `test_valuator_price_fx.py` (seed: the AAPL company of `test_valuator_analysis._seed`, financials `currency` set to `EUR`, close 110 USD on 2026-05-29):
  - `test_usd_company_unchanged`: the plain USD seed → `fx_rate is None`, `listing_price == current_price == 150.0`, `valuation_currency == price_currency == "USD"`.
  - `test_eur_company_close_converted`: EUR `rate_to_usd` 1.10 on 2026-05-29 → `current_price == approx(100.0)`, `margin_of_safety == approx(intrinsic_value_after_governance / 100.0)`, `listing_price == 110.0`, `price_currency == "USD"`, `valuation_currency == "EUR"`, `fx_rate == approx(1 / 1.10)`, `price_date == date(2026, 5, 29)`, `sanity_check.market_pe` computed on 100.
  - `test_nearest_prior_rate_is_used`: EUR rate only on 2026-05-26 (1.10) and 2026-05-30 (2.0) → `current_price == approx(100.0)`.
  - `test_no_rate_on_or_before_close_date_gives_no_price`: EUR rate only on 2026-06-01 → `current_price is None`, `margin_of_safety is None`, `margin_verdict(...) == "n/a"`, every grid cell `margin_of_safety is None`, `market_pe is None`, exactly one `analysis.price_fx_missing` log.
  - `test_null_listing_currency_uses_close`: `prices_daily.currency` NULL → `current_price == 110.0`, `fx_rate is None`.
  - `test_analyze_with_preloaded_inputs_converts`: `analyze(..., company=bulk_load_valuation_inputs(...)["AAPL"])` gives the same `current_price` as the per-ticker path (screener second pass).
  - In `test_reporting_analysis_json.py`: `test_sidecar_carries_the_price_conversion_fields` — keys `valuation_currency`, `listing_price`, `price_currency`, `fx_rate`, `price_date` present, `price_date == "2026-05-29"` (ISO string from the writer's `_json_default`); `schema_version == 1`.
- [ ] **Step 2: Run** them — Expected: FAIL.
- [ ] **Step 3: Implement** Decision 6 in `analyze`: `converted = price_in_valuation_currency(inputs)`; `current_price = converted.price`; populate the new fields. Update the `Analysis` and `ValuationInput` docstrings (`current_price`: newest close converted into the valuation currency).
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_valuator_price_fx.py tests/unit/test_reporting_analysis_json.py tests/unit/test_valuator_isolation_golden.py tests/unit/test_screener_second_pass_golden.py`, then the full suite — Expected: PASS, goldens untouched.
- [ ] **Step 5: Commit** `feat(#222): margin of safety on the price in the valuation currency`.

### Task 4: Report header and conversion line; holding marks

**Files:**
- Modify: `src/bot/reporting/templates/analysis.md.j2:3,11-16`
- Test: `tests/unit/test_reporting_analysis.py`, `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Consumes: Task 3 `Analysis` fields.

- [ ] **Step 1: Write the failing tests.**
  - `test_header_shows_the_valuation_currency`: `analysis` fixture `dataclasses.replace(..., currency="USD", valuation_currency="EUR")` → header line contains `currency EUR`.
  - `test_price_conversion_line_only_when_converted`: with `fx_rate=1/1.10, listing_price=110.0, price_currency="USD", valuation_currency="EUR", current_price=100.0, price_date=date(2026,5,29)` → md contains `- **Price conversion:** close 110.00 USD × 0.909091 = 100.00 EUR (rates on or before 2026-05-29)`; with `fx_rate=None` → no `Price conversion` substring.
  - `test_missing_rate_line`: `current_price=None, margin_of_safety=None, listing_price=110.0, price_currency="USD", valuation_currency="EUR", price_date=...` → contains `has no exchange rate into EUR on or before 2026-05-29`.
  - `test_mark_holdings_stores_the_converted_price` in `test_portfolio_marks.py`: default valuator (no `analyze_fn`), seeded with the file's existing `_seed_benchmarks` + `_seed_company`, then `UPDATE financials_annual SET currency = 'EUR'`, close updated to 110 USD, an EUR row in `currencies` — an EUR-reporting holding with a 110 USD close and EUR rate 1.10 → the persisted mark's `price == approx(100.0)`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** Decision 7 in the template. No change in `marks.py` (it already reads `analysis.current_price`).
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_portfolio_marks.py tests/unit/test_valuator_isolation_golden.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(#222): report shows the valuation currency and the price conversion`.

### Task 5: ADR 0005, CONTEXT.md and the atlas

**Files:**
- Modify: `docs/adr/0005-currency-handling-and-valuation-currency.md` (Status), `CONTEXT.md` (Margin of safety), `docs/pipeline/analyze.d2` (`inputs.load` label, edges `duckdb.prices_daily -> inputs.load`, `inputs.load -> sensitivity.grid`, `inputs.load -> verdict.mos`, `inputs.load -> sanity_check.multiples`, `verdict.mos` label; a `duckdb.currencies -> inputs.load` edge with an `@table currencies` store if the board lacks it), `docs/pipeline/portfolio.d2:57` (`adr_0005` gap: the price conversion is now implemented, §1 is not), `docs/pipeline/analyze-inputs.d2` (`loaded` text, `prices_daily -> loaded` edge, `out` text), `docs/pipeline/analyze-verdict.d2` (`verdict_given` text, the no-price edge), `docs/pipeline/models/analyze.tla` / `analyze.view.js` (`TheCompanyIsLoaded`, `TheTickerHasNoPrice` labels, and the action comments they cite).
- Test: `tests/unit/test_pipeline_diagram.py`, `tests/unit/test_pipeline_subboards.py`, `tests/unit/test_pipeline_models.py`

- [ ] **Step 1: Write the failing tests** in `test_pipeline_subboards.py`: `test_analyze_boards_say_the_close_is_converted` — `analyze.d2`, `analyze-inputs.d2` and `analyze-verdict.d2` each contain `valuation currency` in the text that names the close, and `analyze-verdict.d2` / `analyze.view.js` `TheTickerHasNoPrice` label ends with `[no close, a close at most 0, or no exchange rate]`; in `test_pipeline_diagram.py`: `portfolio.d2` `adr_0005` gap no longer says "prices converted into the valuation currency) are still not implemented"; an ADR test (`tests/unit/test_currency_valuation.py`): ADR 0005 Status mentions `#222`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Edit** the boards, model labels (the board's edge first line must equal the model step label, as the existing tests enforce), ADR and CONTEXT. Label copy: `TheTickerHasNoPrice`: `"the verdict reads the margin of safety (MoS) [no close, a close at most 0, or no exchange rate]"`; `TheCompanyIsLoaded`: `"the company, its newest annual figures, history, close in the valuation currency and sector multiples are loaded"`.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_analyze_model_replay.py` — Expected: PASS. `python3 docs/pipeline/check.py` fails only on the stale `rendered.sha256`.
- [ ] **Step 5: Commit** `docs(#222): ADR 0005 and the atlas record the price conversion`.
- [ ] **Step 6 (orchestrator, after push):** download the `pipeline-render` artifact of the push's `pipeline-diagram` run (`gh run download <id> -n pipeline-render`), copy the SVGs and `rendered.sha256` into `docs/pipeline/`, run `python3 docs/pipeline/check.py` (PASS), commit `docs(#222): render` naming the run id.

## Assumptions

Technical decisions taken without a written source (listed for the PR description):

- A1. **`price_date` on `Analysis`.** The brief asks the report to show "the rate date" but lists only four new fields. The close's date is added as `price_date`; rates are taken on or before it. Rejected: the actual rate rows' dates (a cross rate mixes two rows that may carry different dates).
- A2. **The warning key** in the existing `warned: set[str | None]` is `"price_fx:<listing>/<valuation>"`. Rejected: a second `warned` parameter (changes every caller's signature for one event).
- A3. **The warning is logged by the loaders, not by `analyze`.** `analyze(company=...)` (screener second pass) receives no `warned` set; the loaders do. Rejected: logging in `analyze` (one event per company in the screener).
- A4. **The bulk FX query is always issued** when any ticker is kept, so the query count is the same for an all-USD and a mixed set. An empty-array bind was run against DuckDB 1.5.3 and returns `[]`.
- A5. **The header keeps the word "currency"** and prints the valuation currency; changing the label would move every USD golden, which the first acceptance criterion forbids.
- A6. **`Analysis.currency` (from `companies.currency`) stays** in the sidecar; retiring it is ADR 0005 §1, out of scope.

## Grilling

- Rounds: 1 (the revision added no task and changed no seam). Griller model: fable.
- Questions: 14. Sources: ISSUE 5 (Q2, Q10, Q12, Q13 partly, Q9 with CODE), CODE 9 (Q1 `analysis.py:716`; Q3 `reference/currencies.py:49-54`; Q5 isolation and second-pass seeds are USD in `companies` and `financials_annual`; Q6 `valuator/sensitivity.py:268-309`, `analysis.py:635`; Q7 `reporting/analysis_json.py:20-23`; Q8 `portfolio/sync.py:126-131` computes `close * rate_price / rate_pos` then `quantity * close_in_pos`; Q9 `portfolio/marks.py:131` shares one `warned` set per run; Q11 `tests/unit/test_portfolio_marks.py:67-102`; Q14 `.github/workflows/pipeline-diagram.yml:34` runs `check.py` in the `render` job), DOC 0, NO SOURCE 4 (A1–A4 above, Q4 verified by running the bind).
- Plan changes: Task 2 also switches `analyze` to the converted price so each commit is green; full suite at each task; one normalisation (`normalize_currency`) for codes; warning carries both rates; test fixtures and the sidecar date string named.
- Issues opened: #234 (no staleness bound on the nearest-prior rate; the brief fixes `get_fx_rate` semantics, so it is out of scope here).
