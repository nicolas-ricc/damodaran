# 0011 — Viewer styled with precompiled DaisyUI

## Status

Accepted (2026-11-07). Implemented (2026-11-07, issue #257).

The code is in src/bot/web/static/: daisyui.css (vendored), theme.css, app.css and VERSIONS,
plus scripts/vendor_daisyui.sh. The design system is described in docs/DESIGN.md.

## Context

The viewer (src/bot/web/) was styled by a hand-written stylesheet, the "Rim" system. Every
control, from the filter links to the facts strip, was custom CSS that one maintainer had to
write, test and keep consistent. The repository is Python-only: there is no Node, no
package.json and no front-end build step, and the site is a static output of `bot site`
published to GitHub Pages (ADR 0008). Any styling approach has to fit that: it must not add
a toolchain, and it must not make the published pages depend on a third party at runtime.

## Decision

Vendor the precompiled DaisyUI stylesheet and style the viewer with its components.

- **Vendored at a pinned version.** `scripts/vendor_daisyui.sh` downloads `daisyui.css` for a
  pinned DaisyUI version (`DAISYUI_VERSION`, currently 5.7.50) and checks it against a pinned
  SHA-256 (`DAISYUI_SHA256`). On a mismatch it writes nothing and exits with an error. The
  result is committed as `src/bot/web/static/daisyui.css`, and one line in
  `src/bot/web/static/VERSIONS` records the version and licence.
- **One custom theme.** `src/bot/web/static/theme.css` defines a single theme,
  `[data-theme="synthwave"]`: the colour variables, radius 0 and the `--border`, `--depth`
  and `--noise` settings. It loads after `daisyui.css`. The viewer is dark only.
- **`app.css` keeps only what DaisyUI has no component for.** That is layout, typography,
  the fonts and the chart rules. Its rules read DaisyUI variables (`--color-base-100`,
  `--color-primary` and so on) instead of defining a palette of their own.
- **Supersedes the Rim system.** The "Visual system" consequence of ADR 0008 no longer
  applies; docs/DESIGN.md is rewritten for this system.

## Alternatives considered

**Tailwind standalone CLI with a build step.** DaisyUI's own documentation assumes Tailwind,
and the standalone CLI would let the repository compile only the components it uses, which
shrinks the stylesheet. It does so by adding a platform-specific binary to download and
pin, a build step in CI and in every local checkout, and a Tailwind configuration to
maintain. For one maintainer and a viewer this small, that is more machinery than the saved
bytes are worth.

**The full Node toolchain.** npm, a lockfile, and a bundler would give the same compiled
output and easy upgrades. They also bring a second ecosystem into a Python repository: a
runtime to install, a dependency tree to audit and update, and a new class of CI failures,
all to produce one CSS file.

**The CDN.** Linking DaisyUI (and the Tailwind browser compiler it needs for utilities) from
a CDN needs no vendoring at all. It makes every page view depend on a third-party host at
runtime, compiles styles in the visitor's browser, and lets the site change or break
without a commit in this repository. A static, committed site should render from its own
files.

## Consequences

- The whole component stylesheet ships even though the viewer uses a fraction of it:
  `daisyui.css` is about 1.1 MB uncompressed. GitHub Pages serves it compressed, but it is
  still the largest asset of the site.
- Theme changes are edits to `src/bot/web/static/theme.css`. A test reads the variables of
  that file, so docs/DESIGN.md has to follow.
- Upgrading DaisyUI means editing the two pins in `scripts/vendor_daisyui.sh`
  (`DAISYUI_VERSION` and `DAISYUI_SHA256`), running the script, and editing the `daisyui`
  line in `src/bot/web/static/VERSIONS`, in the order the script header gives. The script is
  not run in CI; a test checks that the committed `daisyui.css` matches the pinned SHA-256,
  so a hand edit of the vendored file is caught.
- `.impeccable/design.json` still describes the previous system until the tool that
  generates it is run again. It is not edited by hand.
