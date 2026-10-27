# 0008 — Read-only web viewer over committed analysis JSON

## Status

Accepted (2026-10-04). Implemented (2026-10-04, `bot site` in src/bot/web/site.py and
.github/workflows/site.yml; issue #92).

## Context

Spec §15 left the web dashboard out of scope: the bot is CLI and local. Reading a
shortlist of analyses still means opening one Markdown or HTML report per company. A
public, read-only page that lists the analysed companies and shows why each got its
verdict is useful and does not require operating the bot from a browser.

## Decision

A static site, built by `bot site` and published to GitHub Pages on every push to
`master`. It is a read-only surface; the bot stays CLI and local (spec §15 still
excludes an operating dashboard).

- **Source of data: a JSON sidecar, not the DB.** `bot analyze` writes
  `reports/<date>/analysis/<TICKER>.json` (`schema_version` 1) next to the Markdown and
  HTML reports. The `.gitignore` lets only those files through. The DuckDB file is local,
  large and not committed; a CI runner cannot rebuild it, and the site should not depend
  on it. The sidecar carries everything the pages show, so the site is a pure function of
  committed files.
- **CI does not run `analyze`.** The runner has no DuckDB, no EDGAR/Tiingo access and no
  keys. Analysis runs locally; its output is committed. CI only runs ruff, mypy, pytest,
  then `bot site`, then deploys.
- **No env vars for `bot site`.** `bot site --out site --reports-dir reports --base-url /`
  reads files only. `--base-url` is `/<repo>/` on Pages.
- **Output.** An index, 30 `rows/` fragments (htmx swaps `<tbody>`), 30 `l/` full list pages
  (the `href` of filter and sort links, so they work with JavaScript disabled), and `c/`
  and `f/` pages per ticker and date. `viewer.js` is small and optional.
- **Verdict.** One reading of the MoS, from `margin_verdict` (single source), shared by
  the reports and the site.
- **Safety.** `bot site` never deletes `out_dir` itself, only its children, and refuses a
  non-empty directory that is not a previous site output, or one that contains
  `--reports-dir`. The file stem is the ticker identity; a sidecar whose `analysis.ticker`
  disagrees, or whose analysis lacks a field the viewer reads, is skipped with a warning.

## Consequences

- Manual prerequisite, once: Settings -> Pages -> Source = GitHub Actions. Without it the
  deploy job fails.
- Published analyses are public. Only commit sidecars you are willing to show.
- The viewer is only as fresh as the last commit of `reports/*/analysis/*.json`. Since
  2026-10-24 the weekly cron job (`scripts/weekly.sh`) runs `bot analyze --from-screen` and
  `scripts/publish_site.sh` pushes the sidecars to `master` from a detached worktree, so the
  site refreshes every Saturday without a manual commit.
- Changing the sidecar shape means bumping `SCHEMA_VERSION` and teaching `web/index.py`
  to handle or skip older versions.
- Visual system: the viewer uses the Rim theme documented in `docs/DESIGN.md` (dark only,
  Switzer and Geist Mono), not the hand-drawn kraft system of the explanatory pieces. Chart
  labels are HTML and the drivers and scenario grid are tables, so no text scales with the
  pane; the facts strip and the pairs reflow on the detail pane's own width (container
  queries). Filter and sort swaps keep keyboard focus on the activated control, and the
  detail pane announces one line per company instead of the whole analysis.
