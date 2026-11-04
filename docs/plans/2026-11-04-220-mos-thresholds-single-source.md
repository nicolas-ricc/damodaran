# MoS verdict thresholds defined once — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the margin-of-safety (MoS) verdict thresholds `MOS_UNDERVALUED = 1.3` and `MOS_FAIR = 1.0` once, in `bot.reporting.analysis_report`, and make the report, the sidecar, the site and the pipeline boards read them from there.

**Architecture:** The two constants move from `bot.web.views` to `bot.reporting.analysis_report`, next to `margin_verdict`, which compares against them. `bot.web.views` and `bot.web.svg` import them; `views` keeps the names importable, so `from bot.web.views import MOS_FAIR` still works. Every `@const` on the pipeline boards that cites `bot.web.views.MOS_*` is re-pointed at `bot.reporting.analysis_report.MOS_*`, and the boards are re-rendered. No output changes.

**Tech Stack:** Python 3 (pytest, ruff, mypy --strict), d2 v0.9.0 for the boards (`docs/pipeline/build.sh` or the `pipeline-render` CI artifact).

**Spec:** issue #220 and its Agent Brief comment.

## Global Constraints

- The thresholds keep their values: `MOS_UNDERVALUED = 1.3`, `MOS_FAIR = 1.0`. Changing them or making them configurable is out of scope (#220).
- Report, sidecar and site output stay byte-identical. Existing output tests (`test_reporting_*`, `test_web_*`) are not edited.
- `grep -n "1\.3" src/bot/reporting src/bot/web` finds only the constant's definition among Python sources (see Assumption A2 for the CSS hits).
- Never edit an SVG or `docs/pipeline/rendered.sha256` by hand.
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py` all pass.

## Decisions

1. **Home of the constants:** `bot.reporting.analysis_report`, defined just above `margin_verdict`, with a `#:` doc comment and no annotation, the style of `views.py:55-57` and `analysis_json.py:12` (no `Final` anywhere in `src/`). The brief names this module; `analysis_json` and `views` already import `margin_verdict` from it, so it adds no new dependency edge. `reporting` does not import `web` today (`grep -rn bot.web src/bot/reporting` is empty; `analysis_report.py:16-24` imports only jinja2 and `bot.valuator`), and `views` already imports `analysis_report` (`views.py:15-25`), so the new `svg` import cannot close a cycle. No tool enforces the direction; this plan only keeps it.
2. **`views` keeps the names** by importing them (`from bot.reporting.analysis_report import MOS_FAIR, MOS_UNDERVALUED, ...`). Its own uses (`ValueLine.fair`, `.undervalued`, the explanation sentence, the axis points) keep working unchanged, and so does `tests/unit/test_pipeline_diagram.py:43`.
3. **`VERDICT_TEXT`** in `views` builds the undervalued and fair texts as `margin_verdict(MOS_UNDERVALUED)` and `margin_verdict(MOS_FAIR)`. `margin_verdict(0.0)` (overvalued) stays: `0.0` is a sample below the fair threshold, not a threshold.
4. **`svg.value_line` tick labels** read `f"fair {MOS_FAIR:.1f}×"` and `f"undervalued {MOS_UNDERVALUED:.1f}×"`, the same format `views.py:236-238` uses. Output stays `fair 1.0×` / `undervalued 1.3×` (pinned by `tests/unit/test_web_svg.py:89-90`). `svg` imports the constants from `bot.reporting.analysis_report`.
5. **Boards:** every MoS `@const` is re-pointed, not only the three boards the brief lists. Today six boards cite `bot.web.views.MOS_*`: `analyze.d2`, `analyze-verdict.d2`, `pipeline.d2`, `site.d2`, `site-scan.d2`, `site-views.d2`. The issue's Fix says "point the atlas `@const` annotations at it", and a board citing `views` would again send a reader to a module that only re-exports. `analyze-flags.d2`, which the brief lists, carries no MoS `@const` (its only `1.0` is `_DEFENSIVE_BETA`), so it does not change.
6. **`_REQUIRED_CONSTS`** in `tests/unit/test_pipeline_diagram.py` follows the boards: each `"bot.web.views.MOS_*"` becomes `"bot.reporting.analysis_report.MOS_*"`. This is a doc-structure test, not an output test; the brief's own board requirement forces it. The parser fixtures in `tests/unit/test_pipeline_check.py`, which only use the string as sample input, stay.
7. **Lesson (done in Task 1, where the line moves):** `docs/leccion/index.html:762` cites `src/bot/reporting/analysis_report.py:185` for `margin_verdict`. The constants push `margin_verdict` down; update the line number to the new one (`check.py` warns otherwise).

## Review Focus

- Someone changes `MOS_UNDERVALUED` and the report or the site keeps the old cut → Task 1's test calls `margin_verdict` at the constants, and Task 2's guard forbids another `1.3` literal.
- Someone re-adds `MOS_UNDERVALUED = 1.3` in `views` → Task 2's test asserts `views.MOS_UNDERVALUED is analysis_report.MOS_UNDERVALUED` and that the only definition is in `analysis_report` (AST scan).
- The site's tick labels drift from the threshold → Task 2 formats them from the constants; `test_web_svg.py:89-90` pins the text.
- A board keeps citing `bot.web.views.MOS_*` → Task 3's `_REQUIRED_CONSTS` change plus a test that no board cites `bot.web.views.MOS_`.
- The committed render goes stale → `check.py` hash check and the `pipeline-diagram` workflow.

## Assumptions

- **A1. All MoS citations move (Decision 5).** Rejected: only `analyze.d2` and `analyze-verdict.d2`, leaving the site boards citing a re-export.
- **A2. The grep criterion is read for MoS literals.** `src/bot/web/static/app.css` contains `1.3fr` and `1.3rem` (layout units). They are not MoS thresholds and stay. The executable guard scans `*.py`, `*.j2` and `*.html` under `src/bot/reporting` and `src/bot/web`.
- **A3. The guard for "only the definition" is a text scan** of every `*.py`, `*.j2` and `*.html` under `src/bot/reporting` and `src/bot/web` for the token `1.3` (regex `(?<![\d.])1\.3(?![\d])`), the executable form of the issue's grep: exactly one hit, the `MOS_UNDERVALUED` line of `analysis_report.py`. A text scan rather than an AST scan, because the svg tick label carries `1.3` inside a string. Module-level assignments to `MOS_UNDERVALUED` / `MOS_FAIR` are counted with `ast` (exactly one each, in `analysis_report`). `1.0` is too common (`(x - 1.0) * 100`) to forbid globally; the definition count, the `VERDICT_TEXT` assertion and the svg label pin its sites.
- **A4. Each task's commit passes the full gate**, except eval tests written ahead for later tasks (stage 3 commits all evals before implementation). Rejected: per-file test runs only.
- **A5. The text-scan guard's failure message names the rule** ("MoS thresholds live in bot.reporting.analysis_report; import MOS_UNDERVALUED/MOS_FAIR"), so a contributor who legitimately needs a non-MoS `1.3` in a template sees why it failed and can add an exemption to the test. Rejected: a silent allow-list today, with no hits to allow.

---

### Task 1: Constants and `margin_verdict` in `analysis_report`

**Files:**
- Modify: `src/bot/reporting/analysis_report.py:185-193`
- Test: `tests/unit/test_mos_thresholds.py` (new)

**Interfaces:**
- Produces: `bot.reporting.analysis_report.MOS_UNDERVALUED = 1.3`, `MOS_FAIR = 1.0` (floats, unannotated); `margin_verdict(margin_of_safety: float | None) -> str` (unchanged signature) compares with them.

- [ ] **Step 1: Write the failing test** `test_margin_verdict_reads_the_constants` (no monkeypatching):

```python
from bot.reporting.analysis_report import MOS_FAIR, MOS_UNDERVALUED, margin_verdict

def test_margin_verdict_reads_the_constants() -> None:
    assert margin_verdict(MOS_UNDERVALUED) == "potentially undervalued"
    assert margin_verdict(MOS_FAIR) == "around fair value"
    assert margin_verdict(MOS_FAIR - 1e-9) == "potentially overvalued"
    assert margin_verdict(MOS_UNDERVALUED - 1e-9) == "around fair value"

def test_threshold_values_unchanged() -> None:
    assert (MOS_UNDERVALUED, MOS_FAIR) == (1.3, 1.0)
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_mos_thresholds.py -q` → FAIL (ImportError on `MOS_FAIR`).
- [ ] **Step 3:** Define the constants above `margin_verdict` with a `#:` comment ("Margin-of-safety thresholds of :func:`margin_verdict`; the site reads them too."), and replace the `1.3` / `1.0` comparisons by them, keeping the `None` branch first and `>=` on both cuts (`analysis_report.py:187-192`). Update the lesson's `src/bot/reporting/analysis_report.py:185` (`docs/leccion/index.html:762`) to `margin_verdict`'s new line.
- [ ] **Step 4:** Run the test → PASS; then the full gate: `uv run pytest -q` (the Task 2/3 eval tests excepted, if they already exist), `uv run ruff check .`, `uv run mypy src`, `python3 docs/leccion/check.py` (0 errors, 0 warnings).
- [ ] **Step 5:** Commit `refactor(#220): MoS thresholds live next to margin_verdict`.

### Task 2: `views` and `svg` read the constants

**Files:**
- Modify: `src/bot/web/views.py:15-57`, `src/bot/web/svg.py:17-25,151-152`
- Test: `tests/unit/test_mos_thresholds.py`

**Interfaces:**
- Consumes: Task 1's constants.
- Produces: `bot.web.views.MOS_UNDERVALUED` / `MOS_FAIR` remain importable (same objects).

- [ ] **Step 1: Write the failing tests:**
  - `test_views_reexports_the_report_constants`: `views.MOS_UNDERVALUED is analysis_report.MOS_UNDERVALUED` and the same for `MOS_FAIR`; `VERDICT_TEXT[Verdict.UNDERVALUED] == margin_verdict(MOS_UNDERVALUED)`, `VERDICT_TEXT[Verdict.FAIR] == margin_verdict(MOS_FAIR)`.
  - `test_thresholds_defined_once`: AST scan of every `*.py` under `src/bot/reporting` and `src/bot/web`; module-level `Assign`/`AnnAssign` targets named `MOS_UNDERVALUED` or `MOS_FAIR` occur only in `src/bot/reporting/analysis_report.py`, once each.
  - `test_no_other_mos_literal`: text scan per A3; the only hit is `src/bot/reporting/analysis_report.py` on the line that assigns `MOS_UNDERVALUED`.
- [ ] **Step 2:** Run → FAIL (`views` defines its own constants; `views.py:40` and `svg.py:152` hold `1.3` literals).
- [ ] **Step 3:** In `views.py` import `MOS_FAIR`, `MOS_UNDERVALUED` from `bot.reporting.analysis_report` in the existing import block, delete the local definitions (`views.py:55-57`), and use them in `VERDICT_TEXT` (Decision 3). In `svg.py` import them from `bot.reporting.analysis_report` and format the two tick labels (Decision 4).
- [ ] **Step 4:** `uv run pytest -q` (Task 3's eval tests excepted, if they already exist), `uv run mypy src`, `uv run ruff check .` → clean.
- [ ] **Step 5:** Commit `refactor(#220): the site reads the MoS thresholds from the report`.

### Task 3: Boards and lesson cite the single definition

**Files:**
- Modify: `docs/pipeline/analyze.d2:234`, `analyze-verdict.d2:36-38`, `pipeline.d2:33`, `site.d2:89`, `site-scan.d2:48-50`, `site-views.d2:32-34`; their `.svg`; `docs/pipeline/rendered.sha256`
- Test: `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_CONSTS`, new `test_no_board_cites_views_mos`)

- [ ] **Step 1: Failing tests:** in `_REQUIRED_CONSTS`, replace every `"bot.web.views.MOS_UNDERVALUED"` / `"bot.web.views.MOS_FAIR"` by `"bot.reporting.analysis_report.MOS_UNDERVALUED"` / `"...MOS_FAIR"` (boards `pipeline`, `analyze`, `site`, `site-scan`, `site-views`, `analyze-verdict`). Add `test_no_board_cites_views_mos`: no `.d2` under `docs/pipeline` contains `bot.web.views.MOS_`.
- [ ] **Step 2:** `uv run pytest tests/unit/test_pipeline_diagram.py -q` → FAIL on those boards.
- [ ] **Step 3:** `sed` the directive text `@const bot.web.views.MOS_` → `@const bot.reporting.analysis_report.MOS_` in the six `.d2` files. Visible labels do not change.
- [ ] **Step 4:** Render. Preferred: push the branch and take `*.svg` + `rendered.sha256` from the `pipeline-render` artifact of the `pipeline-diagram` run on that push (`gh run download <id> -n pipeline-render`), as #218 did; those are CI's own bytes. Fallback: `docs/pipeline/build.sh` with d2 v0.9.0 installed by the README's install line. `rendered.sha256` hashes the `.d2` sources only (`build.sh` last line), so SVG bytes never affect it. Commit the SVGs of the six changed boards plus the hash; PNGs are git-ignored.
- [ ] **Step 5:** `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py` (0 errors, 0 warnings), `uv run pytest -q` → all pass.
- [ ] **Step 6:** Commit `docs(#220): boards cite the MoS thresholds where margin_verdict defines them`.

## Grilling

One round (griller model: fable). The revision added no task and changed no seam, so no second round ran. 16 questions. Sources: ISSUE 4, CODE 15, DOC 3. Questions often cite more than one source. Two questions (12, 16) had no source and became technical assumptions. No spec ambiguity, no out-of-scope issue.

| # | Question (short) | Answer |
|---|---|---|
| 1 | Acceptance criteria, and how the report/sidecar read the constants | ISSUE (Agent Brief, nicolas-ricc): "A test monkeypatches nothing and asserts `margin_verdict(MOS_UNDERVALUED)`, `margin_verdict(MOS_FAIR)` and a value just below `MOS_FAIR` give the three verdicts." / "`grep -n \"1\\.3\" src/bot/reporting src/bot/web` finds only the constant's definition." / "Report, sidecar and site output unchanged (existing tests pass untouched)." / "Pipeline check and full suite pass." → Tasks 1, 2, 2, 3. CODE: `analysis_report.py:239` and `analysis_json.py:27` call `margin_verdict`, so both read the constants through it with no edit. |
| 2 | Templates with `1.3` | CODE: `grep -rn "1\.3" src/bot/reporting src/bot/web` finds `analysis_report.py:189`, `svg.py:152`, `views.py:40,56` and `app.css:210,220,222`. No template. |
| 3 | `VERDICT_TEXT` strings | CODE: `views.py:39-44` already builds them as `margin_verdict(1.3)` / `margin_verdict(1.0)`, so the strings come from the same function. `test_web_views.py:49-52` pins the round trip and `"potentially undervalued"`. |
| 4 | Operators | CODE: `analysis_report.py:189,191` use `>=` on both cuts. Neither the test nor the behaviour changes. |
| 5 | Import direction / cycles | CODE: `analysis_report.py:16-24` imports jinja2 and `bot.valuator` only. `views.py:15-25` already imports `analysis_report`. No tool enforces the direction (Decision 1 reworded). |
| 6 | Grep command, other files, who agreed to A2 | ISSUE: the grep above. ISSUE (Agent Brief): "No other `1.3` / `1.0` MoS literal remains in `src/bot/reporting` or `src/bot/web`." This backs reading the criterion as MoS literals only. CODE: the only non-Python hits are the three `app.css` lines. |
| 7 | Inventory of `bot.web.views.MOS_` in docs | CODE: twelve lines, all `@const` directives: `analyze-verdict.d2:36-38`, `analyze.d2:234`, `pipeline.d2:33`, `site-scan.d2:48-50`, `site-views.d2:32-34`, `site.d2:89`. None in `docs/leccion/`. |
| 8 | Line-number citations | CODE: only `docs/leccion/index.html:762` carries a line number. `models/*.tla` and `plano/part-meta.js` cite `path: symbol`. `docs/leccion/check.py:49-51` only warns on a moved line. DOC `docs/pipeline/README.md` (Directives): "`@symbol` dotted path…", no line numbers. The lesson update moved into Task 1. |
| 9 | How `@const` is resolved | DOC `docs/pipeline/README.md`: "`@const` … Checked by `tests/unit/test_pipeline_diagram.py`". CODE: `test_pipeline_diagram.py:819-837` imports the module and gets the attribute. `analysis_report` is importable wherever the suite runs. |
| 10 | Render bytes and the hash | CODE: `build.sh` last line hashes `*.d2` only. DOC README: "Rendering happens in the `pipeline-diagram` workflow … (artifact `pipeline-render`)". Task 3 Step 4 now prefers the artifact. |
| 11 | Why `views` re-exports | CODE: `views.py:129,133,236-238,256` use the constants, so `views` must import them anyway. The re-export is a consequence, not a request. `test_pipeline_diagram.py:43,1026-1031` keeps working untouched. |
| 12 | Green at each commit | NO SOURCE → technical assumption A4. |
| 13 | Other names that carry the cuts | CODE: `ValueLine.fair` / `.undervalued` (`views.py:129,133`) are `price * MOS_*`. `svg.value_line` takes its geometry from them (`svg.py:102`). No other name. |
| 14 | `#:` and annotation style | CODE: `views.py:55-57` (`#:` comment, unannotated) and `analysis_json.py:12`. No `Final` in `src/`. Decision 1 updated. |
| 15 | `margin_verdict(None)` | CODE: `analysis_report.py:187-188` returns `"n/a"` first. Covered by `test_reporting_analysis_json.py:95` and `test_pipeline_diagram.py:1031`. |
| 16 | Guard false positives and future procedure | CODE: no template hit today (Q2). NO SOURCE for the procedure → technical assumption A5. |

Assumptions declared: A1-A5 above. Issues opened: none.
