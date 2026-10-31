---- MODULE site ----
(* One analysis sidecar, reports/<date>/analysis/<TICKER>.json, from the publish
   script through the site workflow and `bot site` to the live viewer. *)

VARIABLES phase, worktree, committedFiles, committed, onMaster, workflowRan,
          wrote, row, page, failed, baseUrl, skip, margin, verdict

vars == << phase, worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* The checkout holds the sidecar and other local changes. *)
CheckoutFiles == {"sidecar", "other"}

EndPhases == {"nothing_new", "push_failed", "ci_failed", "out_refused", "skipped", "live"}

(* The margin of safety bands, as margin_verdict in src/bot/reporting/analysis_report.py
   writes them into the sidecar's verdict text. *)
TextOf(m) ==
  CASE m = "no price" -> "n/a"
    [] m = "below 1.0" -> "potentially overvalued"
    [] m = "1.0 to 1.3" -> "around fair value"
    [] m = "1.3 or more" -> "potentially undervalued"
    [] OTHER -> "n/a"

(* VERDICT_TEXT inverted: verdict_from_text in src/bot/web/views.py. *)
FromText(t) ==
  CASE t = "potentially undervalued" -> "undervalued"
    [] t = "around fair value" -> "fair"
    [] t = "potentially overvalued" -> "overvalued"
    [] OTHER -> "na"

(* The rule of CONTEXT.md "Verdict", from the margin of safety itself. *)
ThresholdVerdict(m) ==
  CASE m = "1.3 or more" -> "undervalued"
    [] m = "1.0 to 1.3" -> "fair"
    [] m = "below 1.0" -> "overvalued"
    [] m = "no price" -> "na"
    [] OTHER -> "none"

Init ==
  /\ phase = "written"
  /\ worktree = {}
  /\ committedFiles = {}
  /\ committed = FALSE
  /\ onMaster = FALSE
  /\ workflowRan = FALSE
  /\ wrote = FALSE
  /\ row = FALSE
  /\ page = FALSE
  /\ failed = "none"
  /\ baseUrl = "raw"
  /\ skip = "none"
  /\ margin = "unread"
  /\ verdict = "none"

(* scripts/publish_site.sh: the `find reports -path 'reports/*/analysis/*.json'` line *)
PublishFindsTheSidecar ==
  /\ phase = "written"
  /\ phase' = "found"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* scripts/publish_site.sh: checkout --detach, reset --hard, clean -fd of .cache/site-publish, then the cp loop *)
PublishCopiesItIntoTheResetWorktree ==
  /\ phase = "found"
  /\ phase' = "in_worktree"
  /\ worktree' = {f \in CheckoutFiles : f = "sidecar"}
  /\ UNCHANGED << committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* scripts/publish_site.sh: `git diff --cached --quiet` true, echo "no new analyses", exit 0 *)
TheSidecarIsAlreadyOnMaster ==
  /\ phase = "in_worktree"
  /\ phase' = "nothing_new"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* scripts/publish_site.sh: `git commit` after `git add -- reports`; only the copied sidecars are staged *)
PublishCommitsTheSidecar ==
  /\ phase = "in_worktree"
  /\ phase' = "committed"
  /\ committedFiles' = worktree
  /\ committed' = TRUE
  /\ UNCHANGED << worktree, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* scripts/publish_site.sh: `git push` fails, "push failed (is the SSH key usable without an agent?)", exit 1 *)
ThePushFails ==
  /\ phase = "committed"
  /\ phase' = "push_failed"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* scripts/publish_site.sh: `git push -q origin HEAD:master` succeeds *)
ThePushSucceeds ==
  /\ phase = "committed"
  /\ phase' = "on_master"
  /\ onMaster' = TRUE
  /\ UNCHANGED << worktree, committedFiles, committed, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: `on: push: branches: [master]` starts the build job; step `uv sync --frozen` succeeds *)
DependenciesInstall ==
  /\ phase = "on_master"
  /\ phase' = "installed"
  /\ workflowRan' = TRUE
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv sync --frozen` fails; the job stops *)
DependencyInstallFails ==
  /\ phase = "on_master"
  /\ phase' = "ci_failed"
  /\ workflowRan' = TRUE
  /\ failed' = "sync"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, wrote, row, page, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run ruff check .` passes *)
RuffPasses ==
  /\ phase = "installed"
  /\ phase' = "linted"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run ruff check .` fails; the job stops *)
RuffFails ==
  /\ phase = "installed"
  /\ phase' = "ci_failed"
  /\ failed' = "ruff"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run mypy src` passes *)
MypyPasses ==
  /\ phase = "linted"
  /\ phase' = "typed"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run mypy src` fails; the job stops *)
MypyFails ==
  /\ phase = "linted"
  /\ phase' = "ci_failed"
  /\ failed' = "mypy"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run pytest -q` passes *)
PytestPasses ==
  /\ phase = "typed"
  /\ phase' = "tested"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run pytest -q` fails; the job stops *)
PytestFails ==
  /\ phase = "typed"
  /\ phase' = "ci_failed"
  /\ failed' = "pytest"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: step `uv run bot site --out site --base-url ...`; src/bot/web/site.py: build, first line `normalize_base_url` *)
BotSiteNormalisesTheBaseUrl ==
  /\ phase = "tested"
  /\ phase' = "base_url_set"
  /\ baseUrl' = "normalised"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, skip, margin, verdict >>

(* src/bot/web/site.py: _prepare_out_dir raises ValueError (holds the reports, not a directory, or not empty without the marker) before it writes *)
TheOutputDirIsUnsafe ==
  /\ phase = "base_url_set"
  /\ phase' = "out_refused"
  /\ failed' = "site"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, baseUrl, skip, margin, verdict >>

(* src/bot/web/site.py: _prepare_out_dir empties the folder and writes the MARKER file *)
TheOutputDirIsReady ==
  /\ phase = "base_url_set"
  /\ phase' = "out_ready"
  /\ wrote' = TRUE
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, row, page, failed, baseUrl, skip, margin, verdict >>

(* src/bot/web/index.py: scan, `_skip(path, "folder name is not an ISO date")` *)
TheFolderIsNotADate ==
  /\ phase = "out_ready"
  /\ phase' = "skipped"
  /\ skip' = "folder not a date"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/index.py: scan, `TICKER_RE.fullmatch(ticker)` fails, `_skip(...)` *)
TheStemIsNotATicker ==
  /\ phase = "out_ready"
  /\ phase' = "skipped"
  /\ skip' = "stem not a ticker"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/index.py: read_sidecar returns None on an OSError/ValueError or a non-object JSON (scan then continues) *)
TheSidecarIsNotReadable ==
  /\ phase = "out_ready"
  /\ phase' = "skipped"
  /\ skip' = "unreadable"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/index.py: read_sidecar returns None on an unsupported schema_version (scan then continues) *)
TheSchemaVersionIsWrong ==
  /\ phase = "out_ready"
  /\ phase' = "skipped"
  /\ skip' = "schema version"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/index.py: scan, `analysis.get("ticker") != ticker`, `_skip(...)` *)
TheTickerDoesNotMatch ==
  /\ phase = "out_ready"
  /\ phase' = "skipped"
  /\ skip' = "ticker mismatch"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/index.py: scan appends the AnalysisRef *)
TheSidecarIsUsable ==
  /\ phase = "out_ready"
  /\ phase' = "usable"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* src/bot/web/site.py: _renderable, row_view or detail_view raises KeyError/TypeError/ValueError/IndexError, the analysis is dropped *)
TheAnalysisLacksAField ==
  /\ phase = "usable"
  /\ phase' = "skipped"
  /\ skip' = "not renderable"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, margin, verdict >>

(* src/bot/web/site.py: _renderable keeps the analysis *)
TheAnalysisHasEveryField ==
  /\ phase = "usable"
  /\ phase' = "renderable"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* src/bot/web/views.py: row_view reads data["verdict"] through verdict_from_text; margin_verdict wrote that text *)
TheMarginIsAtLeastOnePointThree ==
  /\ phase = "renderable"
  /\ phase' = "row"
  /\ row' = TRUE
  /\ margin' = "1.3 or more"
  /\ verdict' = FromText(TextOf("1.3 or more"))
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, page, failed, baseUrl, skip >>

(* src/bot/web/views.py: row_view reads data["verdict"] through verdict_from_text; margin_verdict wrote that text *)
TheMarginIsFromOneToOnePointThree ==
  /\ phase = "renderable"
  /\ phase' = "row"
  /\ row' = TRUE
  /\ margin' = "1.0 to 1.3"
  /\ verdict' = FromText(TextOf("1.0 to 1.3"))
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, page, failed, baseUrl, skip >>

(* src/bot/web/views.py: row_view reads data["verdict"] through verdict_from_text; margin_verdict wrote that text *)
TheMarginIsBelowOne ==
  /\ phase = "renderable"
  /\ phase' = "row"
  /\ row' = TRUE
  /\ margin' = "below 1.0"
  /\ verdict' = FromText(TextOf("below 1.0"))
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, page, failed, baseUrl, skip >>

(* src/bot/web/views.py: row_view reads data["verdict"] through verdict_from_text; margin_verdict wrote that text *)
TheAnalysisHasNoPrice ==
  /\ phase = "renderable"
  /\ phase' = "row"
  /\ row' = TRUE
  /\ margin' = "no price"
  /\ verdict' = FromText(TextOf("no price"))
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, page, failed, baseUrl, skip >>

(* src/bot/web/site.py: build, list_page(all_rows, ...) renders every row *)
TheListPagesShowTheRow ==
  /\ phase = "row"
  /\ phase' = "listed"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

(* src/bot/web/site.py: build calls _write_company for each entry *)
TheCompanyPagesAreWritten ==
  /\ phase = "listed"
  /\ phase' = "pages"
  /\ page' = TRUE
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, failed, baseUrl, skip, margin, verdict >>

(* .github/workflows/site.yml: job `deploy` (needs: build) runs actions/deploy-pages after upload-pages-artifact *)
GitHubPagesDeploysTheSite ==
  /\ phase = "pages"
  /\ phase' = "live"
  /\ UNCHANGED << worktree, committedFiles, committed, onMaster, workflowRan, wrote, row, page, failed, baseUrl, skip, margin, verdict >>

Done ==
  /\ phase \in EndPhases
  /\ UNCHANGED vars

Next ==
  PublishFindsTheSidecar
  \/ PublishCopiesItIntoTheResetWorktree
  \/ TheSidecarIsAlreadyOnMaster
  \/ PublishCommitsTheSidecar
  \/ ThePushFails
  \/ ThePushSucceeds
  \/ DependenciesInstall
  \/ DependencyInstallFails
  \/ RuffPasses
  \/ RuffFails
  \/ MypyPasses
  \/ MypyFails
  \/ PytestPasses
  \/ PytestFails
  \/ BotSiteNormalisesTheBaseUrl
  \/ TheOutputDirIsUnsafe
  \/ TheOutputDirIsReady
  \/ TheFolderIsNotADate
  \/ TheStemIsNotATicker
  \/ TheSidecarIsNotReadable
  \/ TheSchemaVersionIsWrong
  \/ TheTickerDoesNotMatch
  \/ TheSidecarIsUsable
  \/ TheAnalysisLacksAField
  \/ TheAnalysisHasEveryField
  \/ TheMarginIsAtLeastOnePointThree
  \/ TheMarginIsFromOneToOnePointThree
  \/ TheMarginIsBelowOne
  \/ TheAnalysisHasNoPrice
  \/ TheListPagesShowTheRow
  \/ TheCompanyPagesAreWritten
  \/ GitHubPagesDeploysTheSite
  \/ Done

Spec == Init /\ [][Next]_vars

(* Cites: site.yml runs only on a push to master; publish_site.sh pushes HEAD:master. *)
\* A sidecar reaches the viewer only through a commit pushed to master.
ViewerOnlyFromMaster ==
  page => onMaster

(* Cites: publish_site.sh: `diff --cached --quiet` exits 0 before `git commit`. *)
\* A publish with nothing new makes no commit, so no site workflow runs.
NothingNewNoWorkflow ==
  (phase = "nothing_new" => ~committed) /\ (workflowRan => (committed /\ onMaster))

(* Cites: publish_site.sh: worktree reset --hard and clean -fd, then only reports/*/analysis/*.json copied and `git add -- reports`. *)
\* The publish commit holds sidecars only, never the checkout's other changes.
OnlySidecarsCommitted ==
  committedFiles \subseteq {"sidecar"}

(* Cites: site.yml: steps run in order in job build; deploy needs build. *)
\* Any failing workflow step deploys nothing.
FailedStepDeploysNothing ==
  failed # "none" => (phase # "live" /\ ~page)

(* Cites: site.py _prepare_out_dir: every ValueError is raised before the MARKER is written. *)
\* An unsafe output directory is refused and nothing is written to it.
UnsafeOutputUntouched ==
  phase = "out_refused" => ~wrote

(* Cites: index.py scan and read_sidecar skip; site.py _renderable drops; build makes rows and pages from the kept entries only. *)
\* A sidecar that cannot be used or rendered never becomes a row or a page.
SkippedNeverARow ==
  skip # "none" => (~row /\ ~page)

(* Cites: analysis_json.py writes margin_verdict(mos); views.py row_view reads it back with verdict_from_text. *)
\* Every listed company has one verdict, read from its sidecar, that matches its margin of safety.
OneVerdictFromTheMargin ==
  row => (verdict = ThresholdVerdict(margin) /\ verdict # "none")

(* Cites: site.py build: normalize_base_url is its first line, before _prepare_out_dir. *)
\* Nothing is written before the base address of the site is normalised.
BaseUrlFirst ==
  (wrote \/ page) => baseUrl = "normalised"

====
