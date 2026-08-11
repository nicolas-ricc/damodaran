export const meta = {
  name: 'build-investment-bot-m5',
  description: 'Build M5 portfolio (IBKR TWS API via ib_async) + #53 screener perf, in dependency order with TDD',
  whenToUse: 'After M2/M3/M4/M6 are built on build/backlog-m2-m6, to autonomously build the M5 chain + #53',
  phases: [
    { title: 'M5 Portfolio' },
    { title: 'M4 Perf' },
  ],
}

const REPO = 'nicolas-ricc/damodaran'
const DIR = '/home/nicolasr/Projects/investment-bot'
const BRANCH = 'build/backlog-m2-m6'

// Strict topological order over the "Blocked by" DAG. Sequential, single working tree,
// so concurrent edits to shared files (schema.sql, cli.py) can never race.
//   #25 -> #26 -> #27 -> #28 -> #29  (M5 chain; #28 also needed #16 which is already done)
//   #53 is independent (screener perf) — appended last.
const ISSUES = [
  { n: 25, phase: 'M5 Portfolio' },
  { n: 26, phase: 'M5 Portfolio' },
  { n: 27, phase: 'M5 Portfolio' },
  { n: 28, phase: 'M5 Portfolio' },
  { n: 29, phase: 'M5 Portfolio' },
  { n: 53, phase: 'M4 Perf' },
]

const RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['status', 'summary', 'testsPassing', 'committed'],
  properties: {
    status: { type: 'string', enum: ['done', 'partial', 'failed'] },
    summary: { type: 'string', description: 'One or two sentences on what was built' },
    testsPassing: { type: 'boolean', description: 'Whether the full pytest suite passes after this change' },
    typeClean: { type: 'boolean', description: 'mypy --strict and ruff clean' },
    committed: { type: 'boolean', description: 'Whether the work was committed' },
    commitSubject: { type: 'string', description: 'The conventional-commit subject used, if committed' },
    filesTouched: { type: 'array', items: { type: 'string' } },
    blocker: { type: 'string', description: 'If partial/failed, what blocked completion' },
    notes: { type: 'string', description: 'Anything the maintainer should know (e.g. deferred work, follow-up)' },
  },
}

// Per-issue extra guidance layered on top of the issue's own agent-brief comment.
function extra(n) {
  if (n === 25) {
    return `
## #25 specifics — READ CAREFULLY
- The issue has MULTIPLE comments. The AUTHORITATIVE brief is the LATEST one titled "Brief superseded — switched from Client Portal API to TWS API". IGNORE the original Client Portal / cp-gateway / Docker / OAuth brief entirely.
- Target the IBKR **TWS API** (socket), NOT the Client Portal REST API. Use the **\`ib_async\`** library: \`$HOME/.local/bin/uv add ib_async\`. Do NOT add or import IBKR's \`ibapi\` (ib_async bundles the protocol).
- \`IbkrClient\` lives in a new \`src/bot/ingest/ibkr.py\`. Connect to \`127.0.0.1\`, default port **7496 (live TWS)**, with host/port/clientId **configurable** (via the existing settings/config mechanism), never hard-coded.
- READ-ONLY ONLY: expose \`accounts()\`, \`positions(account_id)\`, \`cash_balances(account_id)\`, \`trades(account_id, since)\`. NO order-placement methods anywhere. These exact signatures are depended on by #26-#29.
- CI MUST NOT touch a live TWS or open a real socket. Unit-test the data-mapping logic against MOCKED ib_async responses. The live \`accounts()\` smoke test is a MANUAL human step — document it in the README, do not attempt it or gate CI on it.
`
  }
  if (n === 27) {
    return `
## #27 specifics
- Read BOTH the agent brief AND the addendum comment "corporate actions need IBKR Flex, not the TWS socket".
- DELIVER the \`trades\` half: socket-sourced executions via the IbkrClient, incremental on \`max(executed date)\`, de-duped on broker execution id. Mock the client in tests.
- CREATE the \`corporate_actions\` table but treat population as DEFERRED (out of scope here — needs IBKR Flex Web Service, not the socket). Leave it empty/stubbed with a clear NOTE, and say so in result.notes. Do NOT block this issue on corp-action retrieval.
`
  }
  if (n === 53) {
    return `
## #53 specifics
- This is a PERF refactor of the screener second-pass valuator (the deferred half of F7): eliminate the per-candidate N+1 query pattern when the second pass runs the valuator over the top-N shortlist.
- BEHAVIOR-PRESERVING: ranking output must be identical. All existing screener tests MUST stay green. Add a test that proves the second pass no longer issues per-candidate redundant loads (e.g. batched/shared loading), without changing results.
`
  }
  return ''
}

function prompt(it) {
  return `You are implementing ONE issue of the investment-bot backlog. Work in the repo at ${DIR} on the \`${BRANCH}\` branch (do NOT create or switch branches). The M1-M6 foundation is already present on this branch and its full suite (~456 tests) passes.

## Your issue
Run \`gh issue view ${it.n} --repo ${REPO} --comments\` to read the full brief. The authoritative spec is the **Agent Brief comment**, not just the issue body — satisfy every acceptance checkbox in it.
${extra(it.n)}
## Required reading before coding
- \`CONTEXT.md\` (domain language + conventions) and the relevant section of \`docs/superpowers/specs/2026-05-25-investment-bot-design.md\` (e.g. §8.3 for events).
- The existing code your work builds on. Storage schema in \`src/bot/storage/schema.sql\` + \`apply_schema\` in \`src/bot/storage/db.py\`; ingest adapter style in \`src/bot/ingest/{base,fmp,damodaran}.py\`; CLI command registration in \`src/bot/cli.py\`; the valuator entrypoint \`bot.valuator.analysis.analyze\`; reporting render functions in \`src/bot/reporting/\` (jinja2 is already a declared dep). Reuse existing helpers, settings, and logging — do not reinvent them.

## How to work
1. TDD: write failing test(s) first that encode the acceptance criteria, then implement until green.
2. Follow project conventions strictly: full type hints (\`mypy --strict\` clean), \`ruff\` clean, pure functions where possible (accept conn/paths, no global state), Conventional Commits. New \`bot/portfolio/\` code targets high coverage like the screener/valuator. Use \`enum.StrEnum\` and PEP 695 type params (\`class Foo[T]\`, \`type X = ...\`), not \`Generic[T]\`.
3. Declared deps already include: typer, duckdb, polars, pydantic(-settings), httpx, structlog, python-dotenv, openpyxl, xlrd, rich, pyyaml, jinja2, matplotlib, plotly. If you need ANY other third-party package you MUST declare it: \`$HOME/.local/bin/uv add <pkg>\` (and \`uv add --dev types-<pkg>\` for stubs). An undeclared import is a defect even if the venv happens to have it.
4. Verify from the repo root, ALL THREE clean and the FULL suite green (no regressions): \`.venv/bin/python -m pytest -q\`, \`.venv/bin/python -m mypy --strict\`, \`.venv/bin/python -m ruff check src tests\`. Run them yourself and confirm before committing.
5. Commit your work as ONE conventional commit (e.g. \`feat(m5): ...\`). Stage ONLY the files you created or modified for THIS issue — use explicit \`git add <paths>\`, NEVER \`git add -A\`/\`git add .\`/\`git commit -am\`. NEVER stage or touch anything under \`.claude/\`. Do NOT push. Do NOT modify GitHub issue state or labels. Do NOT amend or touch other issues' work.

## If you cannot finish
If a dependency is genuinely missing or the brief is under-specified, do as much as is safely correct, commit what's green, and report status \`partial\`/\`failed\` with a precise \`blocker\`. Never leave the suite red.

## FINISH BY RETURNING THE RESULT
Your FINAL action MUST be a call to the StructuredOutput tool with your result — status, summary, testsPassing, typeClean, committed, commitSubject, filesTouched, and any blocker/notes. Do not end your turn with prose; the workflow only sees the StructuredOutput call. This is mandatory.`
}

const results = []
for (const it of ISSUES) {
  phase(it.phase)
  let r
  try {
    r = await agent(prompt(it), { label: `#${it.n}`, phase: it.phase, schema: RESULT_SCHEMA })
  } catch (e) {
    r = { status: 'failed', summary: 'agent threw (likely no StructuredOutput call)', testsPassing: false, committed: false, blocker: String(e && e.message || e) }
  }
  const rec = { n: it.n, phase: it.phase, ...(r || { status: 'failed', summary: 'no result returned' }) }
  results.push(rec)
  const tag = rec.status === 'done' ? '✓' : rec.status === 'partial' ? '◐' : '✗'
  log(`${tag} #${it.n} [${it.phase}] ${rec.status}${rec.testsPassing ? '' : ' (TESTS NOT GREEN)'} — ${rec.summary || ''}`)
  if (rec.status !== 'done') log(`   ⚠️ #${it.n} blocker: ${rec.blocker || 'unspecified'}`)
}

const done = results.filter(r => r.status === 'done').length
const partial = results.filter(r => r.status === 'partial').length
const failed = results.filter(r => r.status === 'failed').length
log(`M5 build complete: ${done} done, ${partial} partial, ${failed} failed of ${results.length}`)
return { done, partial, failed, results }
