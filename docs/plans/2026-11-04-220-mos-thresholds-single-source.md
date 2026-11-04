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

1. **Home of the constants:** `bot.reporting.analysis_report`, defined just above `margin_verdict`, with a `#:` doc comment. The brief names this module; `analysis_json` and `views` already import `margin_verdict` from it, so it adds no new dependency edge (`reporting` never imports `web`).
2. **`views` keeps the names** by importing them (`from bot.reporting.analysis_report import MOS_FAIR, MOS_UNDERVALUED, ...`). Its own uses (`ValueLine.fair`, `.undervalued`, the explanation sentence, the axis points) keep working unchanged, and so does `tests/unit/test_pipeline_diagram.py:43`.
3. **`VERDICT_TEXT`** in `views` builds the undervalued and fair texts as `margin_verdict(MOS_UNDERVALUED)` and `margin_verdict(MOS_FAIR)`. `margin_verdict(0.0)` (overvalued) stays: `0.0` is a sample below the fair threshold, not a threshold.
4. **`svg.value_line` tick labels** read `f"fair {MOS_FAIR:.1f}×"` and `f"undervalued {MOS_UNDERVALUED:.1f}×"`, the same format `views.py:236-238` uses. Output stays `fair 1.0×` / `undervalued 1.3×` (pinned by `tests/unit/test_web_svg.py:89-90`). `svg` imports the constants from `bot.reporting.analysis_report`.
5. **Boards:** every MoS `@const` is re-pointed, not only the three boards the brief lists. Today six boards cite `bot.web.views.MOS_*`: `analyze.d2`, `analyze-verdict.d2`, `pipeline.d2`, `site.d2`, `site-scan.d2`, `site-views.d2`. The issue's Fix says "point the atlas `@const` annotations at it", and a board citing `views` would again send a reader to a module that only re-exports. `analyze-flags.d2`, which the brief lists, carries no MoS `@const` (its only `1.0` is `_DEFENSIVE_BETA`), so it does not change.
6. **`_REQUIRED_CONSTS`** in `tests/unit/test_pipeline_diagram.py` follows the boards: each `"bot.web.views.MOS_*"` becomes `"bot.reporting.analysis_report.MOS_*"`. This is a doc-structure test, not an output test; the brief's own board requirement forces it. The parser fixtures in `tests/unit/test_pipeline_check.py`, which only use the string as sample input, stay.
7. **Lesson:** `docs/leccion/index.html:762` cites `src/bot/reporting/analysis_report.py:185` for `margin_verdict`. The constants push `margin_verdict` down; update the line number to the new one (`check.py` warns otherwise).

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

---

### Task 1: Constants and `margin_verdict` in `analysis_report`

**Files:**
- Modify: `src/bot/reporting/analysis_report.py:185-193`
- Test: `tests/unit/test_mos_thresholds.py` (new)

**Interfaces:**
- Produces: `bot.reporting.analysis_report.MOS_UNDERVALUED: float = 1.3`, `MOS_FAIR: float = 1.0`; `margin_verdict(margin_of_safety: float | None) -> str` (unchanged signature) compares with them.

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
- [ ] **Step 3:** Define the constants above `margin_verdict` with a `#:` comment ("Margin-of-safety thresholds of :func:`margin_verdict`; the site reads them too."), and replace the `1.3` / `1.0` comparisons by them.
- [ ] **Step 4:** Run the test → PASS; `uv run pytest tests/unit/test_reporting_analysis_json.py -q` → PASS.
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
- [ ] **Step 4:** `uv run pytest tests/unit/test_mos_thresholds.py tests/unit/test_web_svg.py tests/unit/test_web_views.py -q` → PASS; `uv run mypy src` and `uv run ruff check .` → clean.
- [ ] **Step 5:** Commit `refactor(#220): the site reads the MoS thresholds from the report`.

### Task 3: Boards and lesson cite the single definition

**Files:**
- Modify: `docs/pipeline/analyze.d2:234`, `analyze-verdict.d2:36-38`, `pipeline.d2:33`, `site.d2:89`, `site-scan.d2:48-50`, `site-views.d2:32-34`; their `.svg`; `docs/pipeline/rendered.sha256`; `docs/leccion/index.html:762`
- Test: `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_CONSTS`, new `test_no_board_cites_views_mos`)

- [ ] **Step 1: Failing tests:** in `_REQUIRED_CONSTS`, replace every `"bot.web.views.MOS_UNDERVALUED"` / `"bot.web.views.MOS_FAIR"` by `"bot.reporting.analysis_report.MOS_UNDERVALUED"` / `"...MOS_FAIR"` (boards `pipeline`, `analyze`, `site`, `site-scan`, `site-views`, `analyze-verdict`). Add `test_no_board_cites_views_mos`: no `.d2` under `docs/pipeline` contains `bot.web.views.MOS_`.
- [ ] **Step 2:** `uv run pytest tests/unit/test_pipeline_diagram.py -q` → FAIL on those boards.
- [ ] **Step 3:** `sed` the directive text `@const bot.web.views.MOS_` → `@const bot.reporting.analysis_report.MOS_` in the six `.d2` files. Visible labels do not change.
- [ ] **Step 4:** Render: `docs/pipeline/build.sh` with d2 v0.9.0 (install with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix "$HOME/.local"`), or push and take `*.svg` + `rendered.sha256` from the `pipeline-render` artifact (`gh run download`). Commit only the SVGs of boards whose source changed plus the hash; PNGs are git-ignored.
- [ ] **Step 5:** Update the lesson's `analysis_report.py:<line>` for `margin_verdict` to its new line.
- [ ] **Step 6:** `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py` (0 errors, 0 warnings), `uv run pytest -q` → all pass.
- [ ] **Step 7:** Commit `docs(#220): boards cite the MoS thresholds where margin_verdict defines them`.
