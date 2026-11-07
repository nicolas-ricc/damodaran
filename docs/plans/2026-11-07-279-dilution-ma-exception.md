# ShareCountNotDiluting M&A exception (#279) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `.agents/skills/subagent-driven-development` (implementers use `.agents/skills/test-driven-development`) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ShareCountNotDiluting` passes a company whose share-count growth exceeds the cap when the cash it paid for acquisitions over the last `ma_window` reported fiscal years is at least `ma_materiality` of its latest total assets.

**Architecture:** `financials_annual.acquisitions` (added by #278) travels to the verdict in two hops. The engine reads it into a new last field of `_AnnualRow` and `build_company_data` turns it into `CompanyData.acquisitions_history`, the same `_tuple` convention as the other histories. The rule then reads that history plus the existing `CompanyData.total_assets` only on the branch where growth is above the cap.

**Tech Stack:** Python 3, DuckDB, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #279 (design decisions inherited from story #62, `Branch: feature/62-dilution-ma-exception`).

## Global Constraints

- `_AnnualRow` gains a **last** field `acquisitions: float | None`; `_load_all_annual` selects `acquisitions` **last**.
- `CompanyData.acquisitions_history: tuple[float, ...] = field(default_factory=tuple)`, in the trap-detection block, docstring: cash paid for acquisitions per fiscal year, most recent last, outflow positive, years without the datum omitted.
- `ShareCountNotDiluting.__init__(self, max_annual_growth: float = 0.05, ma_window: int = 3, ma_materiality: float = 0.10)`.
- Materiality comparison is inclusive: `ratio >= ma_materiality` passes.
- `skipped` stays `False` in every branch. The pass path at or below the cap, the insufficient-history and non-positive-base paths keep their exact current reasons.
- Every existing `ShareCountNotDiluting` test passes unchanged, including `test_share_count_dilution_cap_is_unconditional`, which asserts `"M&A" not in result.reason` for a company with no acquisitions: no new reason may contain the string `M&A`.
- `tests/unit/test_screener_second_pass_golden.py` passes without regenerating the golden file.
- Do not edit `config/presets/`, `docs/pipeline/`, `docs/plano/`, `docs/leccion/` (issue #280 owns them).
- `uv run pytest -q` passes; `uv run ruff check . && uv run mypy src` is clean.

## Declared technical assumptions

- **Reason wording, fixed here** (`g`, `m` = growth and cap with `:.3f`; `r` = ratio with `:.3f`; `n = len(recent)`; `t = ma_materiality` with `:.3f`):
  - pass: `avg share-count growth {g} > maximum {m}, justified by acquisitions of {r}x total assets over the last {n} fiscal years`
  - fail, ratio below: `avg share-count growth {g} > maximum {m}, not justified: acquisitions of {r}x total assets over the last {n} fiscal years < {t}`
  - fail, empty history: `avg share-count growth {g} > maximum {m}, not justified: no acquisitions reported`
  - fail, total assets `None` or `<= 0`: `avg share-count growth {g} > maximum {m}, not justified: total assets unavailable`
- **`n` is `len(recent)`, not `ma_window`.** A company with two reported years is summed over two, and the sentence must say two. With the issue's examples (three values, window 3) it reads "3", as the issue shows. "Fiscal years" names the reported years summed; years without the datum are omitted upstream (issue: "years without the datum omitted").
- **Check order** on the above-cap branch: empty `recent` first, then total assets. A company with neither reads `no acquisitions reported`.
- **NaN total assets** read as unavailable: the guard is written `total_assets is None or not total_assets > 0`, so a NaN (for which `<= 0` is false) falls into `total assets unavailable` instead of printing `nanx`. Rejected alternative: `total_assets <= 0`, which lets NaN through to the ratio.
- **Net divestitures** (negative values, #278 stores FMP's net divestiture negative) are summed as they are: they reduce the ratio. No clamping. The issue says `sum(recent)`.

## Review Focus

1. A history shorter than the window (e.g. `(300.0,)` with `ma_window=3`) is summed over what exists and the reason says `over the last 1 fiscal years` — Task 2 test.
2. A net divestiture inside the window lowers the ratio below the floor: `(400.0, -350.0)` with total assets 1000 → ratio 0.05 → fails — Task 2 test.
3. `total_assets=0.0` reads `total assets unavailable`, never a division error — Task 2 test.
4. Growth at or below the cap with material acquisitions keeps the exact old pass reason (acquisitions are not consulted) — Task 2 test.
5. A restated annual row carrying acquisitions does not reach the history (the existing `is_restated = FALSE` filter) — Task 1 test seeds one.

---

### Task 1: Engine carries acquisitions to the snapshot

**Files:**
- Modify: `src/bot/screener/types.py` (`CompanyData`, trap-detection block, after `share_count_history`)
- Modify: `src/bot/screener/engine.py` (`_AnnualRow`, `_load_all_annual`, `build_company_data`)
- Test: `tests/unit/test_screener_engine.py`

**Interfaces:**
- Consumes: column `financials_annual.acquisitions DOUBLE` (#278, already on the base branch).
- Produces: `_AnnualRow.acquisitions: float | None` (last positional field); `CompanyData.acquisitions_history: tuple[float, ...]`, default `()`.

- [ ] **Step 1: Update the existing positional SELECTs.** In `test_build_company_data_derives_ratios`, `test_build_company_data_roic_uses_country_tax_rate` and `_load_tst_annual`, append `, acquisitions` after `shares_diluted` in the SELECT.
- [ ] **Step 2: Write the failing tests** in `tests/unit/test_screener_engine.py`:
  - `test_build_company_data_acquisitions_history_drops_missing_years`: three `_AnnualRow`s equal except `acquisitions` = `100.0`, `None`, `300.0` → `cd.acquisitions_history == (100.0, 300.0)`.
  - `test_build_company_data_without_rows_has_empty_acquisitions_history`: `annual=[]` → `cd.acquisitions_history == ()`.
  - `test_load_all_annual_carries_acquisitions`: seed `_seed_sector`/`_seed_company(conn, "AAA")`, `UPDATE financials_annual SET acquisitions = 250.0 WHERE ticker='AAA' AND fiscal_year = <latest seeded year>`, plus a restated row for a later year with `acquisitions = 9999.0`; assert `_load_all_annual(conn)["AAA"][-1].acquisitions == 250.0`, the earlier rows carry `None`, and `9999.0` appears in no row.
- [ ] **Step 3: Run** `uv run pytest -q tests/unit/test_screener_engine.py` — expect the new tests FAIL (`TypeError`/`AttributeError`, `_AnnualRow` takes 13 args) and the three Step-1 tests fail with `TypeError` too.
- [ ] **Step 4: Implement.** Add `acquisitions: float | None` as the last `_AnnualRow` field; append `, acquisitions` after `shares_diluted` in `_load_all_annual`'s SELECT; add the `CompanyData` field with the docstring from Global Constraints; in `build_company_data` compute `acquisitions_history = _tuple([r.acquisitions for r in annual])` beside `share_history` and pass it to `CompanyData`.
- [ ] **Step 5: Run** `uv run pytest -q tests/unit/test_screener_engine.py tests/unit/test_screener_second_pass_golden.py` — expect PASS; `uv run mypy src` clean.
- [ ] **Step 6: Commit** `feat(#279): engine carries acquisitions_history to the snapshot`.

### Task 2: ShareCountNotDiluting lifts the cap on material acquisitions

**Files:**
- Modify: `src/bot/screener/rules.py` (`ShareCountNotDiluting`)
- Test: `tests/unit/test_screener_trap_detection.py` (section `ShareCountNotDiluting`, helpers `_company`, `_benchmarks`)

**Interfaces:**
- Consumes: `CompanyData.acquisitions_history`, `CompanyData.total_assets` (Task 1).
- Produces: `ShareCountNotDiluting(max_annual_growth=0.05, ma_window=3, ma_materiality=0.10)`.

All tests below use `share_count_history=(100.0, 110.0, 121.0)` (growth 0.100 > 0.050) unless stated.

- [ ] **Step 1: Write the failing tests:**
  - `test_share_count_dilution_justified_by_material_acquisitions`: `acquisitions_history=(0.0, 0.0, 300.0)`, `total_assets=1000.0` → `passed is True`, `skipped is False`, `"0.300x total assets" in reason`, `"last 3 fiscal years" in reason`.
  - `test_share_count_dilution_not_justified_by_small_acquisitions`: `(0.0, 0.0, 50.0)`, `1000.0` → `passed is False`, `"0.050x" in reason`, `"not justified" in reason`.
  - `test_share_count_dilution_no_acquisitions_reported`: `acquisitions_history=()`, `total_assets=1000.0` → fails, `"no acquisitions reported" in reason`.
  - `test_share_count_dilution_total_assets_unavailable`: `(0.0, 0.0, 300.0)`, `total_assets=None` → fails, `"total assets unavailable" in reason`.
  - `test_share_count_dilution_zero_total_assets_unavailable`: same with `total_assets=0.0` → fails, `"total assets unavailable" in reason`.
  - `test_share_count_dilution_acquisitions_outside_window_ignored`: `(900.0, 0.0, 0.0, 0.0)`, `ma_window=3`, `1000.0` → fails, `"0.000x" in reason`.
  - `test_share_count_dilution_materiality_is_inclusive`: `ShareCountNotDiluting(ma_materiality=0.05)`, `(0.0, 0.0, 50.0)`, `1000.0` → passes.
  - `test_share_count_dilution_short_history_summed_as_reported`: `(300.0,)`, `1000.0` → passes, `"last 1 fiscal years" in reason`.
  - `test_share_count_dilution_net_divestiture_lowers_ratio`: `(400.0, -350.0)`, `1000.0` → fails, `"0.050x" in reason`.
  - `test_share_count_dilution_nan_total_assets_unavailable`: `(0.0, 0.0, 300.0)`, `total_assets=float("nan")` → fails, `"total assets unavailable" in reason`.
  - `test_share_count_within_cap_ignores_acquisitions`: `share_count_history=(100.0, 103.0, 106.09)`, `(0.0, 0.0, 300.0)`, `1000.0` → `reason == "avg share-count growth 0.030 <= maximum 0.050"`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_screener_trap_detection.py -k share_count` — expect the new pass tests and the reason-content tests FAIL; existing tests PASS.
- [ ] **Step 3: Implement** the new `__init__` signature (store both params as attributes) and the above-cap branch exactly as the "Reason wording" assumption fixes: `recent = company.acquisitions_history[-self.ma_window:]`; empty → fail; `total_assets is None or not total_assets > 0` → fail; else `ratio = sum(recent) / total_assets`, `ratio >= ma_materiality` passes. Rewrite the class docstring's last paragraph: the M&A qualification of spec §6.4 is implemented through cash paid for acquisitions over the last `ma_window` reported fiscal years relative to the latest total assets, inclusive floor `ma_materiality`; drop the sentence saying it is not implemented.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_screener_trap_detection.py tests/unit/test_screener_rules.py tests/unit/test_screener_second_pass_golden.py` — expect PASS; then `uv run pytest -q` and `uv run ruff check . && uv run mypy src`.
- [ ] **Step 5: Commit** `feat(#279): ShareCountNotDiluting lifts the cap on material acquisitions`.

## Grilling

One round (the revisions below are local, the seams did not change), 18 questions, griller model fable.

| # | Answer |
|---|---|
| 1 | CODE: `src/bot/screener/engine.py` `build_company_data`, `total_assets = latest.total_assets` where `latest = annual[-1]`: the latest fiscal year's value; `types.py` declares `total_assets: float \| None`. |
| 2 | ISSUE: "If `ratio >= ma_materiality` (inclusive) the rule passes"; reason examples quoted in the issue. Exact wording of the four strings beyond those examples is a declared assumption. CODE: the golden test renders the shortlist `repr`, it holds no share-count reason. |
| 3 | CODE: `tests/unit/test_screener_second_pass_golden.py` fixture `conn` builds an in-memory DB with `apply_schema`, so the column exists (`schema.sql` lines 126, 136); its seed inserts no `acquisitions`, so every history is empty. ISSUE: "fixture companies have no acquisitions". |
| 4 | CODE: `grep -rn _AnnualRow src tests` lists only `engine.py` and the three sites in `tests/unit/test_screener_engine.py` (lines 151-154, 207-217, 223-232). ISSUE lists the same. |
| 5 | CODE: `engine.py` `_load_all_annual`: `WHERE is_restated = FALSE ORDER BY ticker, fiscal_year`. |
| 6 | CODE: `engine.py` `_tuple` "Drop `None` holes, preserving order". ISSUE (#62 comment, nicolas-ricc): "years without the datum omitted (same convention as the other histories)". Wording "fiscal years" for reported years: declared assumption. |
| 7 | CODE: `src/bot/screener/config.py:43-70`: params passed verbatim as kwargs; defaults cover absent keys. ISSUE: "Do not add params to the presets in this task ... Defaults apply meanwhile." |
| 8 | ISSUE (#62 comment): "All are duration cash-flow facts already positive as outflows" (EDGAR); FMP negated (`src/bot/ingest/fmp.py:540-544`). Negative sum: ISSUE "`ratio = sum(recent) / company.total_assets`". |
| 9 | NO SOURCE → technical assumption: NaN reads as unavailable; test added. |
| 10 | CODE: `tests/unit/test_screener_trap_detection.py:24-31` `_company(**overrides)` forwards any `CompanyData` kwarg. |
| 11 | CODE: same file, test asserts `"had_recent_ma"` absent and `"M&A" not in result.reason` with no acquisitions. ISSUE: "every existing `ShareCountNotDiluting` test still passes unchanged". It stays. |
| 12 | DOC: spec `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §6.4: "Share count creciendo > 5% anual sin M&A justificado". ISSUE (#62 comment) chose cash paid for acquisitions as the source. |
| 13 | ISSUE: "`recent = company.acquisitions_history[-ma_window:]`", independent of the growth series. No alignment required. |
| 14 | CODE: `_AnnualRow` is a frozen `@dataclass` with no defaults (`engine.py:264-278`), so a short positional call raises `TypeError`. |
| 15 | CODE: `tests/unit/test_screener_engine.py:35-37` fixture uses `apply_schema`. |
| 16 | ISSUE: Task 1 and 2 are one issue, one PR; a failed Task 2 is fixed, not abandoned. Golden: see 3. |
| 17 | ISSUE: "`ma_materiality: float = 0.10`" and "`ma_materiality=0.05` with ratio 0.05 passes (inclusive)". |
| 18 | DOC: AGENTS.md lists the skills under `.agents/skills/`; header corrected. |

Source counts: ISSUE 10, CODE 11, DOC 2 (several answers cite more than one), NO SOURCE 1 (technical assumption).
Assumptions added: NaN total assets read as unavailable.
Issues opened: none.
