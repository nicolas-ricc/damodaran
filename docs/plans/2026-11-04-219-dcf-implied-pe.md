# Sanity check: implied P/E from the DCF, market P/E beside it — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the sanity check's implied P/E a model multiple (intrinsic value per share ÷ EPS), like the implied EV/sales already is, and show the market P/E (price ÷ EPS) beside it, labelled as such, in the report, the JSON sidecar, the site detail view and the atlas.

**Architecture:** `SanityCheck` (`src/bot/valuator/analysis.py:69-85`) gains `market_pe`. `_sanity_check` (`analysis.py:614-641`) takes the DCF intrinsic value per share and computes both P/E figures from one EPS. The sidecar is `dataclasses.asdict(analysis)`, so `market_pe` reaches the JSON with no code change there; only its module docstring records the meaning change. The report template, the site's `_sanity` and two d2 boards are projections of the new field. The isolation goldens are patched so that only the P/E rows move.

**Tech Stack:** Python 3 (dataclasses, Jinja2), pytest, d2 v0.9.0 (rendered in CI).

**Spec:** issue #219 and its "Agent Brief" comment.

## Global Constraints

- `implied_pe` = `dcf_result.intrinsic_value / EPS`, with EPS = `net_income / shares`. Guards: net income > 0, shares > 0, EPS > 0. No price needed. `None` when the intrinsic value ≤ 0.
- `market_pe` = `current_price / EPS`, today's `implied_pe` rule: price not `None`, net income > 0, shares > 0, EPS > 0.
- `implied_ev_sales` and `sector_*` do not change (out of scope: EV/sales, sector-multiple region fallback).
- JSON sidecar: `SCHEMA_VERSION` stays `1` (additive key).
- Golden fixtures: only the P/E rows move. The commit that touches them says so.
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` all pass.
- Never edit an SVG or `docs/pipeline/rendered.sha256` by hand. d2 is not on `PATH` here: the render comes from the `pipeline-render` artifact of the `pipeline-diagram` workflow after a push (as in #218).

## Decisions taken here

1. **`intrinsic_value` is `dcf_result.intrinsic_value`, the raw value, not the value after governance.** The brief names `dcf_result.intrinsic_value`, and the EV/sales row uses the raw DCF too (`dcf_result.enterprise_value`).
2. **Field order:** `implied_pe, market_pe, sector_pe, implied_ev_sales, sector_ev_sales`. `market_pe` has no default; `SanityCheck` is built only in `_sanity_check`.
3. **`_sanity_check` signature:** `_sanity_check(current_price: float | None, net_income: float | None, shares: float | None, intrinsic_value: float, enterprise_value: float, revenue: float | None, sector: _SectorMultiples) -> SanityCheck`. Every call passes keywords.
4. **Labels.** Report rows (section 8 table, header kept as is, so the golden diff is the P/E rows only): `P/E implied (DCF)`, `P/E market`, `EV/Sales` (unchanged). Site `_sanity` labels: `P/E implied (DCF)`, `P/E market`, `EV/Sales`. The market row's label carries the word "market"; the column header "Implied" stays because changing it would move a non-P/E line of every golden.
5. **Goldens.** The `.md` goldens are rewritten by `regenerate()` (on master it rewrites them byte-identical, so only the P/E rows move). The `.json` goldens are NOT rewritten by `regenerate()`: on master it adds unrelated hypergrowth keys. Instead, each golden JSON's `analysis.sanity_check` object is replaced with the current one, and the file re-dumped with `json.dumps(payload, indent=2, allow_nan=False) + "\n"` (the sidecar's own format; key order is preserved). One-off command, not committed code:

   ```bash
   uv run python - <<'EOF'
   import json, tempfile
   from pathlib import Path
   from tests.unit.test_valuator_isolation_golden import CASES, FIXTURES, _render, _run
   for case in CASES:
       with tempfile.TemporaryDirectory() as tmp:
           markdown, sidecar = _render(_run(case, Path(tmp)))
       (FIXTURES / f"{case}.md").write_text(markdown, encoding="utf-8")
       path = FIXTURES / f"{case}.json"
       golden = json.loads(path.read_text(encoding="utf-8"))
       golden["analysis"]["sanity_check"] = json.loads(sidecar)["analysis"]["sanity_check"]
       path.write_text(json.dumps(golden, indent=2, allow_nan=False) + "\n", encoding="utf-8")
   EOF
   ```

6. **Atlas.** `analyze.d2` `sanity_check.multiples` label and a new edge `dcf.blend -> sanity_check.multiples: "intrinsic value per share"`; `analyze-verdict.d2` edge `verdict_given -> sanity_checked` second and third lines. The first line of that edge is the model's step label and stays. No TLA+ change: no state or step changes.

## Review Focus

1. **Positive EPS, negative intrinsic value** (a distressed blend can go ≤ 0): `implied_pe` must be `None`, never a negative multiple; `market_pe` still computed. Test in Task 1.
2. **Price present but no net income / net income ≤ 0** (loss-maker, e.g. the `distressed` golden): both `None`, report shows `—` (`fmt_num(None)`) on both P/E rows. Test in Task 1 (unit) and the distressed golden.
3. **Shares 0 or `None`**: both `None`, no `ZeroDivisionError`. Test in Task 1.
4. **Sidecars written before this change** (no `market_pe` key) read by the site: the site reads `reports/*/analysis/*.json` from earlier runs; `_sanity` must not raise `KeyError`. Test in Task 2.
5. **Old sidecars' `implied_pe` meant the market P/E.** A sidecar without the `market_pe` key is pre-#219, so its `implied_pe` is the market P/E: `_sanity` shows it on the `P/E market` row and `—` on `P/E implied (DCF)` (Assumption A1). Test in Task 2.

---

### Task 1: `SanityCheck.market_pe` and the DCF implied P/E

**Files:**
- Modify: `src/bot/valuator/analysis.py` (`SanityCheck` docstring and fields, `_sanity_check`, the call in `analyze`)
- Modify: `src/bot/reporting/analysis_json.py` (module docstring only)
- Modify: `tests/fixtures/valuator/isolation/*.md`, `*.json` (Decision 5)
- Test: `tests/unit/test_valuator_analysis.py`, `tests/unit/test_reporting_analysis_json.py`

**Interfaces:**
- Produces: `SanityCheck.market_pe: float | None`; `_sanity_check(..., intrinsic_value: float, ...)` (Decision 3); sidecar key `analysis.sanity_check.market_pe`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_valuator_analysis.py` (import `_sanity_check`, `_SectorMultiples` from `bot.valuator.analysis`; a helper builds `_SectorMultiples(region=None, pe=22.0, ev_sales=5.0, op_margin=None, beta_levered=None, erp=None)`):
  - `test_sanity_check_implied_pe_comes_from_the_dcf`: `current_price=100.0, net_income=10.0, shares=1.0, intrinsic_value=150.0, enterprise_value=500.0, revenue=100.0` → `implied_pe == pytest.approx(15.0)`, `market_pe == pytest.approx(10.0)`, `implied_ev_sales == pytest.approx(5.0)`, `sector_pe == 22.0`.
  - `test_sanity_check_without_price_keeps_implied_pe`: same with `current_price=None` → `implied_pe == pytest.approx(15.0)`, `market_pe is None`.
  - `test_sanity_check_non_positive_net_income_gives_no_pe` parametrized `net_income` in `(0.0, -5.0, None)` → both `None`.
  - `test_sanity_check_no_shares_gives_no_pe` parametrized `shares` in `(0.0, None)` → both `None`.
  - `test_sanity_check_non_positive_intrinsic_value_gives_no_implied_pe` parametrized `intrinsic_value` in `(0.0, -3.0)` → `implied_pe is None`, `market_pe == pytest.approx(10.0)`.
  - Update `test_analyze_sanity_check_vs_sector_multiples`: `implied_pe == pytest.approx(analysis.dcf_result.intrinsic_value / eps)` and `market_pe == pytest.approx(analysis.current_price / eps)`, with `eps = 100_000.0 / 15_500.0` (the seed's 2025 net income and diluted shares, both in millions; `Financials` carries no net income). So `market_pe == pytest.approx(23.25)`, the old `implied_pe`.
  - In `tests/unit/test_reporting_analysis_json.py::test_sidecar_carries_every_section_the_viewer_reads`, the key set gains `"market_pe"`.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuator_analysis.py tests/unit/test_reporting_analysis_json.py` — Expected: FAIL (`TypeError` on `intrinsic_value`, missing `market_pe`).

- [ ] **Step 3: Implement** the `SanityCheck` field and docstring (implied P/E = intrinsic value per share ÷ EPS of the latest fiscal year, the DCF's multiple; market P/E = price ÷ that EPS; `_load_latest_financials` reads the latest annual row, not TTM) and `_sanity_check` per Global Constraints; pass `intrinsic_value=dcf_result.intrinsic_value` from `analyze`. Add to the `analysis_json.py` module docstring: since #219, `sanity_check.implied_pe` is the DCF's (intrinsic value per share ÷ EPS) and the market P/E is `sanity_check.market_pe`; sidecars written before carry the market P/E under `implied_pe` and no `market_pe`.

- [ ] **Step 4: Patch the goldens** with Decision 5's command. Check `git diff --stat tests/fixtures` touches only the twelve isolation files, and `git diff tests/fixtures` shows only P/E row values (`.md`) and the `sanity_check` object (`.json`: `implied_pe` changed, `market_pe` added).

- [ ] **Step 5: Run** `uv run pytest -q tests/unit/test_valuator_analysis.py tests/unit/test_reporting_analysis_json.py tests/unit/test_valuator_isolation_golden.py` — Expected: PASS. Then `uv run ruff check . && uv run mypy src`.

- [ ] **Step 6: Commit** `fix(#219): implied P/E from the DCF, market P/E beside it` with a body line: `Isolation goldens: only the P/E rows moved (implied_pe value, market_pe added).`

### Task 2: Report section 8 and the site detail show both P/E rows

**Files:**
- Modify: `src/bot/reporting/templates/analysis.md.j2:143` (section 8 table)
- Modify: `src/bot/web/views.py:347-357` (`_sanity`)
- Modify: `tests/fixtures/valuator/isolation/*.md` (regenerated)
- Test: `tests/unit/test_reporting_analysis.py`, `tests/unit/test_web_views.py`

**Interfaces:**
- Consumes: `SanityCheck.market_pe`, sidecar key `sanity_check.market_pe` (Task 1).

- [ ] **Step 1: Write the failing tests:**
  - `tests/unit/test_reporting_analysis.py::test_render_sanity_check_shows_both_pe_rows(analysis)`: `analysis = dataclasses.replace(analysis, sanity_check=dataclasses.replace(analysis.sanity_check, implied_pe=15.0, market_pe=10.0, sector_pe=22.0))`; `md` contains `"| P/E implied (DCF) | 15.00 | 22.00 |"`, `"| P/E market | 10.00 | 22.00 |"` and a line starting `"| EV/Sales |"`. (`num` is `fmt_num`, two decimals, as the goldens' `| P/E | 23.25 | 22.00 |` shows.)
  - `tests/unit/test_web_views.py::test_detail_from_a_real_analysis`: `[s.label for s in detail.sanity] == ["P/E implied (DCF)", "P/E market", "EV/Sales"]`.
  - `tests/unit/test_web_views.py::test_sanity_of_a_pre_219_sidecar`: `real_sidecar()` with `del payload["analysis"]["sanity_check"]["market_pe"]` and `implied_pe = 23.25`; the detail view builds; `P/E implied (DCF)` value is `"— / 22.00"`, `P/E market` value is `"23.25 / 22.00"`.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_web_views.py` — Expected: FAIL.

- [ ] **Step 3: Implement.** Template: replace the `P/E` row with the two rows of Decision 4 (`implied_pe` then `market_pe`, each vs `sector_pe`). `_sanity`: three `LabelledValue`s, labels per Decision 4. When `"market_pe" not in check` (pre-#219 sidecar), the implied figure is `None` and the market figure is `check["implied_pe"]` (Assumption A1); otherwise both read their own keys.

- [ ] **Step 4: Regenerate the `.md` goldens** with Decision 5's command (re-running it is harmless for the JSON). `git diff tests/fixtures` shows only the P/E rows (one row relabelled, one added) in each `.md`.

- [ ] **Step 5: Run** `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_web_views.py tests/unit/test_valuator_isolation_golden.py tests/unit/test_reporting_html.py` — Expected: PASS.

- [ ] **Step 6: Commit** `fix(#219): report and site show the implied and market P/E` with the body line `Isolation goldens: only the P/E rows moved.`

### Task 3: Atlas — analyze board and analyze-verdict sub-board

**Files:**
- Modify: `docs/pipeline/analyze.d2:241` (`sanity_check.multiples` label), edges near `:346`
- Modify: `docs/pipeline/analyze-verdict.d2:40` (edge `verdict_given -> sanity_checked`, lines 2 onward)
- Test: `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_TEXT["sanity_check.multiples"]`), `tests/unit/test_pipeline_subboards.py` (`_ANALYZE_TEXT["analyze-verdict"]`)

- [ ] **Step 1: Update the pinned phrases (failing):** `_ANALYZE_TEXT["sanity_check.multiples"]` becomes `["intrinsic value per share ÷ earnings per share (EPS)", "market P/E = price ÷ EPS", "net income ÷ diluted shares", "EV ÷ revenue", "decides nothing"]`. `_ANALYZE_TEXT["analyze-verdict"]` gains `"intrinsic value per share ÷ earnings per share (EPS)"` and `"market P/E = price ÷ EPS"`.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py -k "text"` — Expected: FAIL.

- [ ] **Step 3: Edit the boards.** `analyze.d2` `sanity_check.multiples`:
  `"implied multiples, from the DCF, next to the sector's; decides nothing\nimplied price-to-earnings (P/E) = intrinsic value per share ÷ earnings per share (EPS),\nwith EPS = net income ÷ diluted shares; market P/E = price ÷ EPS;\nboth need net income > 0, shares > 0 and EPS > 0;\nimplied P/E needs intrinsic value > 0, market P/E a price; both vs sector pe\nimplied EV ÷ sales = EV ÷ revenue, revenue > 0; vs sector ev_sales"`
  and the edge `dcf.blend -> sanity_check.multiples: "intrinsic value per share"` next to `dcf.ev -> sanity_check.multiples: "EV"`.
  `analyze-verdict.d2` edge: keep line 1, then `implied price-to-earnings (P/E) = intrinsic value per share ÷ earnings per share (EPS), with EPS = net income ÷ diluted shares\nmarket P/E = price ÷ EPS, set beside it\nimplied enterprise value (EV) ÷ sales = EV ÷ revenue`. Node `sanity_checked` second line: `the implied and market multiples sit beside the sector's; this decides nothing`.

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py` — Expected: PASS. `python3 docs/pipeline/check.py` fails only on the stale `rendered.sha256` (render comes from CI).

- [ ] **Step 5: Commit** `docs(#219): analyze boards say the implied P/E comes from the DCF`.

- [ ] **Step 6 (orchestrator, after push):** download the `pipeline-render` artifact of the push's `pipeline-diagram` run (`gh run download <id> -n pipeline-render`), copy the SVGs and `rendered.sha256` into `docs/pipeline/`, run `python3 docs/pipeline/check.py` (PASS), commit `docs(#219): render` naming the run id.

## Assumptions

- **A1. Pre-#219 sidecars on the site.** A sidecar without `sanity_check.market_pe` predates this issue, so its `implied_pe` is the market P/E (`_sanity_check` before #219, `analysis.py:622-632`). The site shows it on the `P/E market` row and `—` on `P/E implied (DCF)`. Rejected: showing the old value under the DCF label (mislabels every published report, against the brief's "labelled as such"), and bumping `SCHEMA_VERSION` (the brief says it stays 1).
- **A2. EPS wording.** The docstrings say "EPS of the latest fiscal year", not "trailing": `_load_latest_financials` (`analysis.py:214-223`) reads the latest non-restated annual row. Rejected: keeping "trailing", which reads as TTM.
- **A3. Commit split.** Task 1 changes the meaning and patches the goldens' values; Task 2 changes the labels. Each commit leaves the suite green. Rejected: one commit (a reviewer could accept the model and reject the copy).
- **A4. Finite multiples.** `json.dumps(..., allow_nan=False)` already serialises `intrinsic_value` and `current_price`; dividing them by a positive finite EPS stays finite for any input the DCF guard admits. No extra guard.

## Grilling

- Rounds: 1 (the revision added no task and no seam: one rule in `_sanity`, one test, wording).
- Questions: 16. Sources: CODE 12, ISSUE 3 (Q2 schema version, Q3 raw intrinsic value, Q12 golden header), NO SOURCE 4 → technical assumptions A1–A4 (Q2 old sidecars, Q7, Q9, Q13). Q2 was answered by the issue for the schema version and by A1 for the display.
- Corrections: `fmt_num(None)` is `—`, not `n/a` (`analysis_report.py:110-113`).
- Issues opened: none.
