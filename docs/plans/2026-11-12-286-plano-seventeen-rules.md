# The architecture plan counts seventeen screener rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every place in the `docs/plano/` sources that states the total number of screener rules says seventeen, matching the seventeen `@register` rules in `src/bot/screener/rules.py`.

**Architecture:** Copy-only edits to five source spots of the architecture plan (`plano.html`), pinned by one new test module. The test takes the rule count from `bot.screener.rules.registered_rules()`, scans `docs/plano/` for the stale wording, checks each of the five new phrases, and runs `build.py` the way `tests/unit/test_dilution_ma_docs.py` already does. Generator logic stays as it is.

**Tech Stack:** Python 3.12 stdlib generator (`docs/plano/build.py`), pytest.

**Spec:** GitHub issue #286 (nicolas-ricc/damodaran), "docs(plano): the architecture plan still counts sixteen screener rules", the triage Agent Brief comment in particular.

## Global Constraints

- The total is seventeen: `grep -c '^@register' src/bot/screener/rules.py` = 17 (seven quality gates, four value indicators, six trap detectors).
- The qarp sentence in `docs/plano/estado.py:85` (`qarp usa dieciséis reglas: omite EV/EBITDA sin comentarlo.`) stays exactly as it is.
- Out of scope: a build-time check that compares the count with the registry, any change to the status plan or the lesson (#277), and any change to the qarp sentence.
- `plano.html`, `estado.html` and `codemap.json` are gitignored build outputs (`.gitignore`). No built artifact is committed.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use Conventional Commits with the `(#286)` scope.

## Exact copy

| File:line | Before | After |
|---|---|---|
| `docs/plano/build.py:95` | `"dieciséis reglas, cero subjetividad"` | `"diecisiete reglas, cero subjetividad"` |
| `docs/plano/part-body.html:106` | `Un embudo de cuatro etapas y dieciséis reglas` | `Un embudo de cuatro etapas y diecisiete reglas` |
| `docs/plano/part-data.js:82` | `Cuatro etapas, dieciséis reglas, cero subjetividad.` | `Cuatro etapas, diecisiete reglas, cero subjetividad.` |
| `docs/plano/part-meta.js:78` | `Las dieciséis reglas del screener` | `Las diecisiete reglas del screener` |
| `docs/plano/iso.py:159` | `>16 reglas</text>` | `>17 reglas</text>` |

Only the count word changes. The rest of each line stays byte-for-byte the same.

## Review Focus

- **The stale wording in another casing or in a build output.** The scan is case-insensitive (`dieciséis|sixteen|16 reglas`, the issue's grep) and covers only tracked sources. The gitignored outputs are left out, because a stale local `estado.html` would otherwise fail the test. Pinned by `test_plano_sources_only_qarp_says_sixteen`.
- **The iso label also feeds `estado.html`.** `build_estado.py` imports `iso`, so the status plan picks up `17 reglas` as well. That is intended: the label states the total. Pinned by `test_build_estado_runs` (exit 0).
- **A future rule added to the registry.** The tests compare with `len(registered_rules())` through a word table, so an 18th rule fails `test_registry_count_matches_plano` loudly. It does not pass silently. This test checks a doc claim in pytest, not in the build, so it stays inside the scope line about build-time checks.

---

### Task 1: The plan sources say seventeen

**Files:**
- Create: `tests/unit/test_plano_rule_count.py`
- Modify: `docs/plano/build.py:95`, `docs/plano/part-body.html:106`, `docs/plano/part-data.js:82`, `docs/plano/part-meta.js:78`, `docs/plano/iso.py:159`

**Interfaces:**
- Consumes: `bot.screener.rules.registered_rules()` (already exists).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_plano_rule_count.py`. Module docstring: `"""The architecture plan counts the screener's seventeen rules (#286)."""`. Use `_ROOT = Path(__file__).resolve().parents[2]` and `_PLANO = _ROOT / "docs" / "plano"`, as the sibling doc tests do.
  - `test_registry_count_matches_plano`: `assert len(registered_rules()) == 17`.
  - `test_plano_sources_only_qarp_says_sixteen`: the tracked files come from `git ls-files docs/plano` (subprocess, `cwd=_ROOT`), minus `fonts/*.b64`. Collect every `(relative path, line)` that matches `re.compile(r"dieciséis|sixteen|16 reglas", re.IGNORECASE)`. Assert that the list equals `[("docs/plano/estado.py", <the estado.py:85 line, stripped>)]`, compared through a substring check on `"qarp usa dieciséis reglas: omite EV/EBITDA sin comentarlo."`.
  - `test_plano_sources_say_seventeen`: parametrized over the five `(file, phrase)` pairs in the "After" column above. Each asserts `phrase in (_PLANO / file).read_text("utf-8")`.
  - `test_build_plano_says_seventeen`: `subprocess.run([sys.executable, str(_PLANO / "build.py")], capture_output=True, text=True, check=False)`. Assert returncode 0. Then read `plano.html` and assert that it contains `diecisiete reglas, cero subjetividad`, `Las diecisiete reglas del screener` and `>17 reglas</text>`, and does not contain `dieciséis reglas, cero subjetividad`.
  - `test_build_estado_runs`: same subprocess call with `build_estado.py`. Assert returncode 0, and assert that `estado.html` contains `>17 reglas</text>`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_plano_rule_count.py -q`
Expected: `test_registry_count_matches_plano` passes. The scan, the five phrases, the plano build check and the estado label check FAIL.

- [ ] **Step 3: Apply the five edits in "Exact copy".**

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_plano_rule_count.py -q && grep -rniE 'dieciséis|sixteen|16 reglas' docs/plano --include='*.py' --include='*.js' --include='*.md' --include='part-*.html'`
Expected: all tests PASS. The grep prints only the `estado.py:85` qarp line.

- [ ] **Step 5: Full suite and lint**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: everything green.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_plano_rule_count.py docs/plano/build.py docs/plano/part-body.html docs/plano/part-data.js docs/plano/part-meta.js docs/plano/iso.py
git commit -m "docs(#286): the architecture plan counts seventeen screener rules"
```
