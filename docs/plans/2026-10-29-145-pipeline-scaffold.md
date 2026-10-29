# Pipeline diagram scaffold (overview board) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `docs/pipeline/` with its checking machinery (citation checker, build script, render workflow, tests) and its first board, `pipeline.d2`: the whole pipeline on one page, rendered by d2 + TALA to a committed `pipeline.svg`.

**Architecture:** d2 sources carry machine-checked citations as `@kind argument` directives in line comments. `docs/pipeline/check.py` (stdlib + `docs/plano/codemap.py`) parses them, resolves `@symbol`/`@table`/`@file`/`link:`, and checks that every board has an SVG and that `rendered.sha256` matches the sources. `tests/unit/test_pipeline_diagram.py` validates the directives that need `bot` importable (`@rule`, `@param`, `@const`, `@enum`), the required citations, and the acronym rule. Rendering never happens in the test suite: `docs/pipeline/build.sh` renders when d2 at the pinned version is on `PATH`, and the `pipeline-diagram` GitHub Actions workflow runs it on every push and uploads the result as an artifact that the executor commits.

**Tech Stack:** Python 3.12 (stdlib for `check.py`), pytest, PyYAML (tests only), bash + shellcheck (`shellcheck-py` is already a dev dependency), d2 `v0.9.0` with its bundled TALA layout, GitHub Actions.

**Spec:** GitHub issue #145 (nicolas-ricc/damodaran), with the story's inherited decisions in #144's two plan comments. The issue body is binding; this plan only fixes names and interfaces the issue leaves open.

## Global Constraints

- Everything lives in `docs/pipeline/`. Boards: `pipeline.d2` now; `refresh.d2`, `screen.d2`, `analyze.d2`, `portfolio.d2`, `site.d2` come in #146–#150. `classes.d2` is not a board. Every board starts with `...@classes`; no board imports another board.
- `classes.d2` defines exactly nine classes in one `classes: { ... }` map: `step` (rectangle), `decision` (diamond), `store` (cylinder), `external` (cloud), `file` (page), `output` (document), `cron` (hexagon), `note` (text), `gap` (text).
- `docs/pipeline/D2_VERSION` is the single line `v0.9.0`. Versions are compared after stripping a leading `v`.
- Render command per board (all `*.d2` except `classes.d2`): `d2 --layout tala --tala-seeds "${TALA_SEEDS:-1}" <stem>.d2 <stem>.svg`, then the same command with `<stem>.png`. Then `rendered.sha256` = sha256 hex digest of the concatenation of all `*.d2` files sorted by name (`LC_ALL=C` order, which is Python's `sorted()` order), written as `<hex>\n`.
- `docs/pipeline/*.png` is git-ignored and never committed. An SVG is never hand-written or hand-edited; it comes from `build.sh` at the pinned version, locally or from the `pipeline-render` artifact of a run whose `.d2` sources are the committed ones.
- English, with `CONTEXT.md` vocabulary exactly (universe, story type, margin of safety, verdict, quality gates, value indicators, trap detection, sector benchmark, coverage gate, measured company, fiscal year, listing / reporting / valuation currency).
- Formulas as plain math, never function names. The first time an acronym appears in a board, its expansion appears in the same label or earlier in the file.
- Directives live only in d2 line comments, never inside a `|md ... |` block string. Several directives may share one comment. A directive trails the line whose visible text it checks; a comment line holding only directives applies to the next non-comment, non-blank line.
- "Shown": one rendering of the value is a substring of the line's visible text after collapsing whitespace runs to one space and mapping `−` (U+2212) to `-`.
- `check.py` is stdlib-only (it may import `docs/plano/codemap.py`). Nothing in the tests invokes d2; a fake `d2` script on `PATH` is allowed.
- Do not touch `src/`. Commits: Conventional Commits `docs(#144): ...` for the board work, as the issue asks (`test(#145)`, `plan(#145)`, `fix(#145)`, `chore(#145)` for the pipeline's own stage commits).
- Quality bar: `uv run ruff check . && uv run mypy src && uv run pytest -q` and `uv run shellcheck docs/pipeline/build.sh .factory/setup.sh` clean.

## Review Focus

1. A `#` inside a quoted d2 label (`"#1 step"`, `style.fill: "#fff"`) is not a comment, so no directive is read from it and no visible text is cut there. Test in Task 1 (`test_hash_inside_quotes_is_not_a_comment`).
2. A one-line markdown block (`note: |md MoS ≥ 1.3 … | {class: note} # @const …`) closes on the same line: the trailing comment's directives are read and the block's text counts as the line's visible text; a multi-line block swallows every `#` and `@` until it closes. Test in Task 1 (`test_one_line_md_block_keeps_trailing_directive`).
3. A misspelled directive kind (`@tabel prices_daily`) must not pass silently: `check.py` reports it as an unknown directive. Test in Task 1 (`test_unknown_directive_kind_is_an_error`).
4. `build.sh` run with no `d2` on `PATH`, or with a `d2` at another version, exits non-zero before writing anything and says which fix applies. Test in Task 2 (`test_build_refuses_without_d2`, `test_build_refuses_wrong_version`).
5. A directive whose value is not shown on its line (`@const bot.web.views.MOS_FAIR` on a line that says nothing about 1.0) fails the suite, naming the board, line and value. Test in Task 3 (`test_every_directive_is_valid` failure message), with a synthetic case in Task 1 for `shown()`.

## Assumptions (declared, not in the issue)

- Error strings are English and start with `<board>:<line>` where a line exists: `pipeline.d2:12 unknown @symbol bot.x.Y`, `pipeline.d2:3 unknown @table foo`, `pipeline.d2:4 missing @file path/x`, `pipeline.d2:5 missing link target refresh.svg`, `pipeline.d2:7 unknown directive @tabel`, `pipeline.d2 has no pipeline.svg`, `rendered.sha256 missing`, `rendered.sha256 is stale: run docs/pipeline/build.sh`. Summary line: `check | <B> boards, <C> citations, <E> errors`.
- `@file` paths resolve against the repository root (`codemap.REPO`), whatever folder `check.py` is pointed at; `link:` targets resolve against the folder being checked.
- `build.sh` works in its own directory (`cd "$(dirname "$0")"`), so a test can copy it with a few `.d2` files to `tmp_path` and run it there against a fake `d2`.
- Build-tooling tests go in a third module, `tests/unit/test_pipeline_build.py`, so the two modules the issue names keep their stated roles.
- Node keys in `pipeline.d2` are fixed here (the tests look them up), see Task 3.
- `build.sh` reads the version as the first `v?[0-9]+\.[0-9]+\.[0-9]+` match in `d2 version`'s output (rejected: first whitespace token), because the exact v0.9.0 output format is not documented anywhere this plan can cite; the real CI run is what proves it.
- Acronym test: an acronym is a token matching `\b[A-Z][A-Z0-9]+\b` or the literal `MoS` in `check.visible(board)`; its expansion counts when the expansion text appears (case-insensitive) anywhere from the start of the board to the end of the line holding the first occurrence. Every such token must be in `_ACRONYMS` or `_ACRONYMS_EXEMPT`; the exempt set is `JSON`, `CSV`, `YAML`, `SVG`, `URL` plus non-acronym capitals the board uses as words or placeholders (`US`, `YYYY`, `MM`, `DD`, `TICKER`, `HTML`, `S`, `P` if they occur). Underscored names such as `BOT_NOTIFIER` do not match (`_` is a word character). Rejected: a hard-coded list with no catch-all, which lets an unlisted acronym through.
- `@enum` is checked against the whole board's visible text, not by `renderings()`; the `site.verdicts` note names the `Verdict` member values `undervalued`, `fair`, `overvalued`, `na` (`src/bot/web/views.py:32-36`) in its text.
- `check.py` imports `codemap` with a `sys.path` insert of `docs/plano`, as `docs/leccion/check.py:13-16` does, and carries its own copy of `indice()` (rejected: importing the lesson's checker, which would couple two independent docs).
- `test_build_refuses_without_d2` runs `build.sh` with `PATH` set to a `tmp_path` bin holding symlinks to `bash`, `cat`, `dirname`, `cut`, `sha256sum`, `sort`, `ls` (resolved with `shutil.which`) and no `d2`.
- `check.py` carries type hints but stays outside mypy, which only checks `packages = ["bot"]` (`pyproject.toml`), as `docs/leccion/check.py` does; ruff covers it.
- Intermediate `pipeline-diagram` runs (before the SVG is committed) are red by design; only the run on the PR head commit must be green.

---

### Task 1: `check.py` — directive parser, renderings, citation checker

**Files:**
- Create: `docs/pipeline/check.py`
- Test: `tests/unit/test_pipeline_check.py` (written in the evals stage; make it pass)

**Interfaces:**
- Produces (module loaded by tests through `importlib.util.spec_from_file_location`):
  - `KINDS: tuple[str, ...] = ("symbol", "table", "file", "rule", "param", "const", "enum")`
  - `class Directive(NamedTuple): kind: str; argument: str; text: str; line: int` — `text` is the visible text of the line it applies to (the line minus its comment, md-block content included), `line` that line's 1-based number.
  - `directives(text: str) -> list[Directive]` — only known kinds.
  - `unknown_directives(text: str) -> list[tuple[str, int]]` — `(@word, line)` for `@word` tokens in comments whose word is not in `KINDS`. `...@classes` is code, not a comment, so it is never seen.
  - `links(text: str) -> list[tuple[str, int]]` — targets of `link:` lines outside md blocks, quotes stripped.
  - `visible(text: str) -> str` — the board with comments removed (md content kept); used by the acronym test.
  - `normalize(text: str) -> str` — collapse whitespace, `−` → `-`.
  - `renderings(value: object) -> set[str]`; `shown(value: object, text: str) -> bool` — a tuple/list is shown when every element is shown; a string when it is a substring.
  - `indice() -> dict[str, tuple[str, int]]` (as `docs/leccion/check.py::indice`), `tablas(schema: str) -> set[str]`, `boards(folder: Path) -> list[Path]` (sorted `*.d2` minus `classes.d2`), `source_hash(folder: Path) -> str`.
  - `revisar(folder: Path, idx: dict[str, tuple[str, int]], tables: set[str]) -> tuple[list[str], int]` — errors and citation count over every board in `folder`, including SVG presence and the hash.
  - `main(argv: list[str] | None = None) -> int` — CLI `python3 docs/pipeline/check.py [dir]`, default its own folder; prints each `error  <msg>`, then the summary; returns 1 on any error.

- [ ] **Step 1: Run the evals module to see it fail**

Run: `uv run pytest -q tests/unit/test_pipeline_check.py`
Expected: FAIL (file `docs/pipeline/check.py` does not exist).

- [ ] **Step 2: Implement `docs/pipeline/check.py`**

Line scanner, one pass, state = "inside md block with delimiter D" or not. Outside a block: walk the line tracking `"`/`'` quotes; a `|md`, `||md` or `|||md` opener (also `|markdown`) starts a block whose closer is the same run of pipes; if the closer appears later on the same line the block ends there and scanning resumes after it; the first unquoted `#` that starts the line or follows whitespace starts the comment. Inside a block, everything up to the closer is content. Directive regex on the comment: `@(\w+)\s+(\S+)`; a comment with directives and no code before it is "pending" and attaches to the next line that has code. `renderings` for a number `v` (bool excluded): `str(v)`; if integral, `str(int(v))`, `f"{int(v):,}"`, and `<n>K`/`<n>M`/`<n>B` for each exact multiple of 1e3/1e6/1e9; `<p>%` where `p = round(v * 100, 9)` printed integral-style when integral, else `repr`; for `abs(v) < 1`, `<b> bps` and `<b>bps` where `b = round(v * 10000, 6)` printed the same way. Hash: `hashlib.sha256(b"".join(p.read_bytes() for p in sorted(folder.glob("*.d2")))).hexdigest()` compared with `rendered.sha256` stripped.

- [ ] **Step 3: Run the module**

Run: `uv run pytest -q tests/unit/test_pipeline_check.py && uv run ruff check docs/pipeline tests/unit/test_pipeline_check.py`
Expected: PASS, ruff clean.

- [ ] **Step 4: Commit** — `git add docs/pipeline/check.py && git commit -m "docs(#144): pipeline citation checker"`

### Task 2: Render tooling — `D2_VERSION`, `build.sh`, workflow, setup, gitignore

**Files:**
- Create: `docs/pipeline/D2_VERSION`, `docs/pipeline/build.sh` (mode 755), `.github/workflows/pipeline-diagram.yml`
- Modify: `.factory/setup.sh` (append after `uv sync --frozen`), `.gitignore` (add `docs/pipeline/*.png`)
- Test: `tests/unit/test_pipeline_build.py` (written in the evals stage; make it pass)

**Interfaces:**
- Consumes: `check.source_hash(folder)` (the test asserts `build.sh`'s `rendered.sha256` equals it).
- Produces: artifact `pipeline-render` with `docs/pipeline/*.svg`, `docs/pipeline/*.png`, `docs/pipeline/rendered.sha256`; workflow name `pipeline-diagram`, job `render`.

- [ ] **Step 1: Run the evals module to see it fail** — `uv run pytest -q tests/unit/test_pipeline_build.py` → FAIL (files missing).

- [ ] **Step 2: Write `build.sh`.** `#!/usr/bin/env bash`, `set -euo pipefail`, `cd "$(dirname "$0")"`. If `command -v d2` fails: stderr `build.sh: d2 is not on PATH. Install d2 $(cat D2_VERSION) (https://d2lang.com/install.sh --version …) or let the pipeline-diagram workflow render.`, exit 1. Compare `d2 version` (first whitespace-separated token, leading `v` stripped) with `D2_VERSION` (leading `v` stripped); on mismatch stderr names both versions, exit 1. Then the render loop and the hash file from the Global Constraints (`LC_ALL=C` glob order; `sha256sum | cut -d' ' -f1`). Nothing is written before both checks pass.

- [ ] **Step 3: Write the workflow** exactly as the issue's "Files" bullet: `on: [push, workflow_dispatch]`, `permissions: contents: read`, `concurrency: {group: pipeline-diagram-${{ github.ref }}, cancel-in-progress: true}`, job `render` on `ubuntu-latest`, steps in order: checkout v4; install (`curl -fsSL https://d2lang.com/install.sh | sh -s -- --version "$(cat docs/pipeline/D2_VERSION)" --method standalone --prefix "$HOME/.local"` then `echo "$HOME/.local/bin" >> "$GITHUB_PATH"`); `d2 version && d2 layout && d2 layout | grep -qw tala`; `docs/pipeline/build.sh`; upload-artifact v4 `if: always()`; `python3 docs/pipeline/check.py`; step named `committed render is current`: `git diff --exit-code -- docs/pipeline/rendered.sha256` and fail if `git ls-files --others --exclude-standard docs/pipeline/*.svg` prints anything.

- [ ] **Step 4: Append to `.factory/setup.sh`** an `if ! curl … --prefix /usr/local; then echo "d2 not installed; the pipeline-diagram workflow renders instead"; fi` block (an `if` condition does not trip `set -e`). Add `docs/pipeline/*.png` to `.gitignore`.

- [ ] **Step 5: Verify** — `uv run pytest -q tests/unit/test_pipeline_build.py && uv run shellcheck docs/pipeline/build.sh .factory/setup.sh && bash -n .factory/setup.sh` → PASS, no output from shellcheck.

- [ ] **Step 6: Commit** — `docs(#144): pipeline render script and workflow`

### Task 3: `classes.d2`, `pipeline.d2`, README, `CONTEXT.md`

**Files:**
- Create: `docs/pipeline/classes.d2`, `docs/pipeline/pipeline.d2`, `docs/pipeline/README.md` (≤ 40 lines)
- Modify: `CONTEXT.md` ("Source of truth": a `docs/pipeline/` bullet — the diagram-first documentation; `check.py` fails when a cited table, file or symbol stops existing)
- Test: `tests/unit/test_pipeline_diagram.py` (written in the evals stage; make it pass except `test_check_py_exits_zero` and `test_each_board_has_a_rendered_svg`, which turn green only after the render in Task 4)

**Interfaces:**
- Consumes: `check.directives`, `check.visible`, `check.shown`, `check.boards`.
- Produces — node keys the tests look up (top level unless dotted), each with `class:` as the first attribute inside its braces or on its own line `{class: X}`:
  - `step`: `refresh`, `screen`, `analyze`, `portfolio`, `site`. Labels: stage name + one-line purpose.
  - `cron`: `daily` (`scripts/daily.sh`), `weekly` (`scripts/weekly.sh`).
  - `external`: `damodaran_data` (Damodaran datasets), `edgar` (Securities and Exchange Commission (SEC) Electronic Data Gathering, Analysis, and Retrieval (EDGAR)), `tiingo` (Tiingo, end-of-day (EOD) prices, default), `stooq` (Stooq, alternative), `fmp` (Financial Modeling Prep, optional: foreign exchange (FX) and non-US), `tws` (Interactive Brokers (IBKR) Trader Workstation (TWS)), `flex` (IBKR Flex, corporate actions), `pages` (GitHub Pages).
  - `store`: container `duckdb` (class none, label `DuckDB (bot.duckdb)`) with one child per table of `schema.sql`, key = table name, `{class: store}`, each line carrying its `# @table <name>`.
  - `file`: `universe_csv`, `industry_mapping_csv`, `presets`, `assumptions`, `sidecars` (`reports/YYYY-MM-DD/analysis/<TICKER>.json`).
  - `output`: `screen_report`, `analysis_reports`, `portfolio_md` (portfolio.md and alerts.md), `notifier_message`, `published_site`.
  - `note`: `site.verdicts`, a one-line md block `|md … |` stating: margin of safety (MoS) ≥ 1.3 potentially undervalued, ≥ 1.0 around fair value, < 1.0 potentially overvalued, n/a without a price; trailing `# @const bot.web.views.MOS_UNDERVALUED @const bot.web.views.MOS_FAIR @enum bot.web.views.Verdict`. If d2 rejects a one-line md block, use a double-quoted label with `class: note` instead and say so in the commit.
  - Cron edges, labels starting with their order number: `weekly -> refresh: "1. bot refresh --all"`, `weekly -> screen: "2. bot screen --preset damodaran_value"`, `weekly -> analyze: "3. bot analyze --from-screen"`, `weekly -> site: "4. scripts/publish_site.sh"`; `daily -> refresh: "1. bot refresh --prices, in rounds until nothing is deferred"`, `daily -> refresh: "2. bot refresh --fx"`, `daily -> portfolio: "3. bot portfolio"`.

Data flows to draw (read from `src/bot/cli.py`, the scripts and the table usage in `src/bot/`; edge label = what flows):
- `refresh`: Damodaran datasets → `damodaran_industry`, `damodaran_country`; EDGAR (+ `universe_csv` tickers, `industry_mapping_csv`) → `companies`, `financials_annual`, `financials_quarterly`, `filings_log`; Tiingo / Stooq / FMP → `prices_daily`; FX → `currencies`; every source writes a row to `refresh_log`. Order inside: Damodaran → fundamentals → prices → FX.
- `screen`: reads `presets` (damodaran_value), `companies`, `financials_annual`, `prices_daily`, `damodaran_industry`, `damodaran_country`, `assumptions`; writes `screener_candidates` (ranked shortlist, run id) and `screen_report` (`reports/YYYY-MM-DD/screen/<preset>.{md,csv}`).
- `analyze`: reads the latest run's passed `screener_candidates` by rank, `companies`, `financials_annual`, `prices_daily`, Damodaran tables, `assumptions` overrides; writes `analysis_reports` (`<TICKER>.md`, `.html`) and `sidecars` (`.json`).
- `site`: `scripts/publish_site.sh` commits `sidecars` to `master`; `.github/workflows/site.yml` runs `bot site` (`bot.web.site.build`) → `published_site` → `pages`.
- `portfolio`: `tws` → `portfolio_snapshots`, `cash_balances`, `trades`; `flex` → `corporate_actions`; reads `prices_daily`, `filings_log`, `holding_marks`, financials for the quality gates and trap detection re-check of held companies; writes `events_log`, `holding_marks`, `portfolio_md`; `bot.notifier.notify_alerts` → `notifier_message` (email or Telegram, when `BOT_NOTIFIER` is set).

Required citations (`_REQUIRED_*["pipeline"]` in the test): `@symbol` `bot.cli.refresh`, `bot.cli.screen`, `bot.cli.analyze`, `bot.cli.portfolio`, `bot.cli.site`, `bot.web.site.build`, `bot.notifier.notify_alerts`; `@table` every table of `schema.sql` (derived); `@file` `src/bot/ingest/universe_default.csv`, `src/bot/ingest/industry_mapping.csv`, `config/presets/damodaran_value.yaml`, `scripts/daily.sh`, `scripts/weekly.sh`, `scripts/publish_site.sh`, `.github/workflows/site.yml`; `@const` `bot.web.views.MOS_UNDERVALUED`, `bot.web.views.MOS_FAIR`; `@enum` `bot.web.views.Verdict`.

README content: what the boards are; build `docs/pipeline/build.sh`; check `python3 docs/pipeline/check.py`; directive table with the seven kinds and who checks each; `D2_VERSION`; rendering happens in the `pipeline-diagram` workflow (artifact `pipeline-render`) or locally when `d2` at that version is on `PATH`; "run `build.sh` after editing a `.d2`; CI fails on a stale SVG".

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_diagram.py` → FAIL (no boards).
- [ ] **Step 2:** Write `classes.d2`, `pipeline.d2`, README, `CONTEXT.md` bullet.
- [ ] **Step 3:** `uv run pytest -q tests/unit/test_pipeline_diagram.py` → everything passes except the two render-dependent tests; `python3 docs/pipeline/check.py` lists only the missing SVG and hash.
- [ ] **Step 4: Commit** — `docs(#144): pipeline overview board`

### Task 4: Render through CI and commit the SVG (controller, not a subagent: it needs `git push` and `gh`)

- [ ] Push; find the `pipeline-diagram` run whose `headSha` is `HEAD`; `gh run watch <id> --exit-status`; on a build failure read `gh run view <id> --log-failed`, fix the source, push again.
- [ ] When the build step is green: `gh run download <id> -n pipeline-render -D /tmp/render`; copy `*.svg` and `rendered.sha256` into `docs/pipeline/`; look at `/tmp/render/pipeline.png`; fix layout in the source if needed (then loop); commit `docs(#144): render pipeline`; push; the run on that commit must be green end to end and its log must show `d2 layout` listing `tala`.
- [ ] `python3 docs/pipeline/check.py` exits 0; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Grilling

- Rounds: 1 (the answers added assumptions and changed no task, seam or step, so there was no second round). Griller model: fable.
- Questions: 17. Answered from ISSUE: 8 (1, 3, 7, 10, 12, 13, 15, plus the "Python is present on the runner" half of 2); CODE: 7 (2, 5, 6, 9, 14, 16, 17); NO SOURCE → technical assumption: 3 (4, 8, 11). Spec ambiguities: 0. Out of scope: 0.
- Assumptions added: version parsing in `build.sh`; acronym regex and exempt set; `@enum` checked against the board text, with the verdict note naming the member values; `codemap` import and `indice()` copy; the PATH construction in the build test; `check.py` outside mypy; intermediate red CI runs.
- Issues opened: none.
