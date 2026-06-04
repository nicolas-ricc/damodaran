export const meta = {
  name: 'build-investment-bot',
  description: 'Implement the 24 ready-for-agent issues (M2/M3/M4/M6) in dependency order with TDD on master atop M1',
  whenToUse: 'After M1 is merged to master, to autonomously build the agent-reachable backlog',
  phases: [
    { title: 'M2 Data' },
    { title: 'M3 Screener' },
    { title: 'M4 Valuator' },
    { title: 'M6 Viz' },
  ],
}

const REPO = 'nicolas-ricc/damodaran'
const DIR = '/home/nicolasr/Projects/investment-bot'

// Strict topological order over the "Blocked by" DAG. Sequential, single working tree,
// so concurrent edits to shared files (schema.sql, cli.py, config.py) can never race.
const ISSUES = [
  { n: 2,  phase: 'M3 Screener' },
  { n: 3,  phase: 'M3 Screener' },
  { n: 18, phase: 'M2 Data' },
  { n: 11, phase: 'M4 Valuator' },
  { n: 22, phase: 'M2 Data' },
  { n: 4,  phase: 'M3 Screener' },
  { n: 5,  phase: 'M3 Screener' },
  { n: 6,  phase: 'M3 Screener' },
  { n: 19, phase: 'M2 Data' },
  { n: 21, phase: 'M2 Data' },
  { n: 12, phase: 'M4 Valuator' },
  { n: 13, phase: 'M4 Valuator' },
  { n: 15, phase: 'M4 Valuator' },
  { n: 7,  phase: 'M3 Screener' },
  { n: 20, phase: 'M2 Data' },
  { n: 14, phase: 'M4 Valuator' },
  { n: 8,  phase: 'M3 Screener' },
  { n: 23, phase: 'M2 Data' },
  { n: 16, phase: 'M4 Valuator' },
  { n: 9,  phase: 'M3 Screener' },
  { n: 10, phase: 'M3 Screener' },
  { n: 17, phase: 'M4 Valuator' },
  { n: 30, phase: 'M6 Viz' },
  { n: 31, phase: 'M6 Viz' },
]

// Issues whose acceptance criteria require recording VCR cassettes against a live API.
// No BOT_FMP_API_KEY is available, so these must use hand-authored synthetic cassettes.
const SYNTH_CASSETTE = new Set([18, 19, 20, 21, 22, 23])

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
    notes: { type: 'string', description: 'Anything the maintainer should know (e.g. synthetic cassette, placeholder, follow-up)' },
  },
}

function prompt(it) {
  const cassette = SYNTH_CASSETTE.has(it.n)
    ? `\n## VCR cassettes — IMPORTANT\nNo BOT_FMP_API_KEY is set and you MUST NOT make live network calls. Where the brief asks for recorded cassettes, hand-author SYNTHETIC VCR cassettes (realistic but fabricated FMP/FX JSON shaped like the real API) so the integration tests run deterministically offline. Add a clear comment/NOTE in the cassette and in your result.notes that these are synthetic and must be re-recorded against the live API with a real key before production use.\n`
    : ''

  return `You are implementing ONE issue of the investment-bot backlog. Work in the repo at ${DIR} on the \`master\` branch. The M1 foundation is already present and its 45 tests pass.

## Your issue
Run \`gh issue view ${it.n} --repo ${REPO}\` to read the full brief (What to build + Acceptance criteria + Blocked by). That brief is your spec — satisfy every acceptance checkbox.

## Required reading before coding
- \`CONTEXT.md\` (domain language + conventions) and \`docs/superpowers/specs/2026-05-25-investment-bot-design.md\` (the section the issue references, e.g. §6.2/§6.5).
- The existing code your work builds on. The adapter pattern lives in \`src/bot/ingest/base.py\`; storage in \`src/bot/storage/db.py\` + \`schema.sql\`; CLI in \`src/bot/cli.py\`; existing adapters \`src/bot/ingest/{damodaran,sec_edgar}.py\` are the reference style. Reuse the existing \`IngestResult\`, \`upsert_*\` helpers, settings, and logging — do not reinvent them.

## How to work
1. TDD: write failing test(s) first that encode the acceptance criteria, then implement until green.
2. Follow project conventions strictly: full type hints (\`mypy --strict\` clean), \`ruff\` clean, pure adapter/functions (no global state, accept conn/paths), VCR cassettes for any HTTP, Conventional Commits. Screener rules (\`src/bot/screener/\`) and valuator (\`src/bot/valuator/\`) target 100% test coverage.
3. Verify with the project's configured tools — check \`pyproject.toml\`/\`README.md\` for exact invocations; defaults: \`.venv/bin/python -m pytest -q\`, \`.venv/bin/python -m mypy --strict src\`, \`.venv/bin/python -m ruff check src tests\`. The FULL suite must stay green (no regressions to the existing 45 tests).
4. Commit your work as ONE conventional commit (e.g. \`feat(m3): ...\`) once green. Do NOT push. Do NOT modify GitHub issue state or labels. Do NOT amend or touch other issues' work.
${cassette}
## If you cannot finish
If a dependency is genuinely missing or the brief is under-specified, do as much as is safely correct, commit what's green, and report status \`partial\`/\`failed\` with a precise \`blocker\`. Never leave the suite red.

Return the structured result describing exactly what you did.`
}

const results = []
for (const it of ISSUES) {
  phase(it.phase)
  const r = await agent(prompt(it), { label: `#${it.n}`, phase: it.phase, schema: RESULT_SCHEMA })
  const rec = { n: it.n, phase: it.phase, ...(r || { status: 'failed', summary: 'no result returned' }) }
  results.push(rec)
  const tag = rec.status === 'done' ? '✓' : rec.status === 'partial' ? '◐' : '✗'
  log(`${tag} #${it.n} [${it.phase}] ${rec.status}${rec.testsPassing ? '' : ' (TESTS NOT GREEN)'} — ${rec.summary || ''}`)
  if (rec.status !== 'done') log(`   ⚠️ #${it.n} blocker: ${rec.blocker || 'unspecified'}`)
}

const done = results.filter(r => r.status === 'done').length
const partial = results.filter(r => r.status === 'partial').length
const failed = results.filter(r => r.status === 'failed').length
log(`Build complete: ${done} done, ${partial} partial, ${failed} failed of ${results.length}`)
return { done, partial, failed, results }
