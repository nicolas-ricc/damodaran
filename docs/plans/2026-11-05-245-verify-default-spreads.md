# Verify `config/default_spreads.yaml` against its sources — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check every row of `config/default_spreads.yaml` against its cited source, using a model different from the one that seeded the file. Then record the result on #213 and #245, fix any mismatch, and stamp the YAML header with a `verified:` line.

**Architecture:** No production code changes. The verification is a subagent run that fetches both sources itself and returns a row-by-row table. The executable part is a set of tests in `tests/unit/test_default_spreads.py`. They pin the per-table `source`/`as_of`, the 15 bracket bounds, and the header's `verified:` line. A YAML row changes only if the verifier finds a mismatch, and it changes to the source's value.

**Tech Stack:** Python 3.12, PyYAML, pytest; WebFetch for the HTML page; `uv run --with pypdf python -I` for the PDF.

**Spec:** issue #245 (parent story #213; the file and loader come from #243, plan `docs/plans/2026-11-05-243-default-spreads.md`).

## Global Constraints

- Sources: ratings page `https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html` (left block, data as of January 2026, `as_of: 2026-01-01`); paper `https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/NewDistress.pdf` (Table 5, pp. 41-42, 10-year column, `as_of: 2009-06-01`).
- These mapping decisions are documented and do not count as mismatches: S&P half of the label; clean bounds, lower inclusive and upper exclusive (`≤ 0.199999` is `< 0.2`); the 10-year column; `BB+` = `BB` row; `D` = `C-` row.
- Verifier model: different from the seeder (Sonnet, #243 stage 4) and from this session (Opus), so **Fable**, with Haiku as the fallback.
- The PDF is downloaded into a new empty directory outside the repo. The extraction script lives in a different directory and runs as `uv run --with pypdf python -I <script> <pdf>`.
- Header line, exact format: `# verified: <YYYY-MM-DD>, every row checked against its source on <model> (#213)`.
- A pinned test value changes only when the source says so, and the commit message names the source line.
- Feature commit message: `docs(#213): default-spread tables verified against their sources`.
- `uv run ruff check . && uv run mypy src` clean; `uv run pytest -q` green.

## Review Focus

1. A copied row (`BB+`, `D`) that drifts from the row it copies after a fix. This is already pinned by `test_repo_lookups` (`probability_for("BB+") == probability_for("BB")`). The pin must survive any fix.
2. A bracket bound typo (e.g. `4.2` instead of `4.25`) that the existing tests would miss, because they only pin ratings and a few lookups. Task 1 pins all 15 `(lower, upper, rating)` triples.
3. A row whose `source` or `as_of` is the other table's value. The existing tests only check `https://` and that the value is a date. Task 1 pins each table's exact URL and date.
4. A header `verified:` line in the wrong format, or one naming the session model instead of the verifier model. Task 1 tests the format, and Task 2 writes the verifier's model.
5. A probability given as a percentage (`81.03`) instead of a decimal. This is caught by the loader's [0, 1] check and by `TABLE_5_TEN_YEAR`.

---

### Task 1: Evals — pin sources, dates, bounds and the header line

**Files:**
- Test: `tests/unit/test_default_spreads.py`

**Interfaces:**
- Consumes: `load_default_spreads(REPO_FILE)`, `CoverageBracket(lower, upper, rating, source, as_of)`, `DefaultProbability(probability, source, as_of)`, `REPO_FILE`.
- Produces: the constants `RATINGS_URL`, `PAPER_URL`, `RATINGS_BRACKETS` (list of `(lower, upper, rating)`), used by Task 2's fixes if any.

- [ ] **Step 1: Write the failing tests**
  - `test_repo_brackets_match_ratings_page`: `[(b.lower, b.upper, b.rating) for b in table.brackets] == RATINGS_BRACKETS` (the 15 triples from the #243 plan's Decision 6 table), and every bracket has `source == RATINGS_URL` and `as_of == date(2026, 1, 1)`.
  - `test_repo_probabilities_cite_table_5`: every probability row has `source == PAPER_URL` and `as_of == date(2009, 6, 1)`.
  - `test_repo_header_carries_verified_line`: the file contains exactly one line matching `^# verified: (\d{4}-\d{2}-\d{2}), every row checked against its source on (\S.*) \(#213\)$`, and the date parses with `date.fromisoformat`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_default_spreads.py -q`. Expected: only `test_repo_header_carries_verified_line` fails, because there is no line yet. The other two pass against the current seed.
- [ ] **Step 3: Commit** `test(#245): evals`.

### Task 2: Independent verification, fixes, header stamp

**Files:**
- Modify: `config/default_spreads.yaml` (header line; any mismatching row)
- Modify, only if a source value differs: `tests/unit/test_default_spreads.py` (`TABLE_5_TEN_YEAR`, `RATINGS_BRACKETS`, `test_repo_lookups` pins)

**Interfaces:**
- Consumes: Task 1's tests.

- [ ] **Step 1: Run the verifier subagent** (model Fable). It works in two phases. First it reads both sources itself and transcribes the left block and the Table 5 10-year column **before** opening `config/default_spreads.yaml`, and it records the page's "data as of" line and the paper's date line. Then it opens the YAML and compares, returning for each of the 15 brackets and each of the 17 probability rows: table, row key, file value, source value, match yes/no. It must also report whether each row's `source` URL is the page the number comes from, whether each `as_of` equals the source date, and whether `BB+ == BB` and `D == C-`.
- [ ] **Step 2: Post the result** on #213 and #245 with both model names (session Opus; verifier Fable), the full table and a one-line verdict.
- [ ] **Step 3: Fix any mismatch** (one that the documented mapping decisions do not explain). Also update `RATINGS_BRACKETS`/`TABLE_5_TEN_YEAR` if the source differs from Decision 6, in the YAML, and in a pinned test value if one is affected. Name the source line in the commit message.
- [ ] **Step 4: Add the header line** `# verified: 2026-11-05, every row checked against its source on <verifier model> (#213)` as the last header comment line, directly before `horizon_years`.
- [ ] **Step 5: Run** `uv run pytest tests/unit/test_default_spreads.py -q`. Expected: all pass. Then run the full gate.
- [ ] **Step 6: Commit** `docs(#213): default-spread tables verified against their sources`.

## Assumptions

Technical decisions taken in plan review (stage 2). Each one names the alternative it rejects.

- **Blind transcription.** The verifier transcribes the sources before it reads the YAML, so that a transcription error shared by the #243 plan and the seed cannot be echoed back. The rejected alternative was handing it the file first. Task 1's pins are copied from Decision 6 and act as a regression net. The verifier's output is what gets compared against the source, and a pin changes when the verifier's source value differs.
- **Live page drift.** The verifier records the ratings page's "data as of" line. If the page has moved past January 2026, every difference is reported as "source updated since seed", not fixed. The issue pins the January 2026 data (`as_of` 2026-01-01). Re-seeding to a newer vintage is not this issue's work, and the verdict would say so. The rejected alternative was re-seeding to the live values.
- **Adjudication.** The documented mapping decisions in the issue body (clean bounds, S&P half, 10-year column, `BB+`=`BB`, `D`=`C-`) are applied by this session to the verifier's raw comparison. The verifier is told about them, and they never count as mismatches.
- **Ordering.** The comment is posted after the verification and before any fix, following the issue's order (steps 3 then 4). If a fix follows, the comment names the row and the fix commit is referenced in the PR.
- **Fallback.** Haiku is used only if launching on Fable fails because of a usage limit or unavailability. The verifier's actual model goes into the header line and the comments.
- **PDF download** uses `curl` into `mktemp -d` under `/tmp`. The script lives in a separate `mktemp -d`. Both are temporary, outside the repo, and removed after the run. A download into `/tmp` was checked to work in this sandbox on 2026-11-05.

## Grilling

- Rounds: 1 (Fable). Questions: 15. Revisions were local (a two-phase verifier, assumptions), so there was no second round.
- Sources: ISSUE 7 (Q4 mapping decisions; Q5 order; Q9 as_of 2009-06-01 is given by the issue; Q12/Q13 commit message prescribed verbatim; Q14 header format prescribed, it points at #213 where the table is posted; Q8 "left block" named by the issue and by the YAML header), CODE 4 (Q6 `tests/unit/test_default_spreads.py:207-222,256-268`, `src/bot/reference/default_spreads.py:222`; Q7 `config/default_spreads.yaml:1-26`: the comment block runs straight into `horizon_years`, with no blank line, and YAML ignores comments; Q15 `src/bot/reference/default_spreads.py:35-54`; Q10 #243 stage-4 comment "model: sonnet (implementers)", with T2 seeding the YAML), NO SOURCE 4 (Q1/Q2 blind transcription, Q3 page drift, Q10 fallback criterion, Q11 download tool), all four technical assumptions above.
- Spec ambiguities: none. Follow-up issues opened: none.
