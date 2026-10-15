# CCA - Cyber-CLI Admin Toolkit

Agent-agnostic toolkit: bin scripts for PATH, skills in SKILL.md format.

## Architecture

```
bin/           # cca-* prefixed scripts, add to PATH via cca-install
lib/           # sourced shell helpers (cca-env.sh: shared project config loader)
skills/        # legacy skills (unchanged until TASK-2), skill-name/SKILL.md format
src/cca/       # unified `cca` Python CLI (uv project at repo root); skills in src/cca/skills/
tests/         # Test scripts (bash + python)
```

## Commands

Run test scripts directly (they are executable), never as `bash tests/...`; new test scripts get `chmod +x`.

| Command | Description |
|---------|-------------|
| `./bin/cca-install bin ~/bin` | Symlink bin scripts to ~/bin |
| `./bin/cca-install skills` | Symlink skills to .claude/skills |
| `tests/run-all.sh` | Run everything: shellcheck, bash tests, ruff, pytest |
| `tests/test-legacy-baseline.sh` | bin/, lib/, root skills/ unchanged vs tag `legacy-baseline` (incl. untracked files) |
| `tests/test-leak-scan.sh` | backlog/ and src/ against the fixture denylist; release check fails closed |
| `tests/test-package.sh [DENYLIST]` | uv build, wheel/sdist content, install smoke into a temp uv tool dir, skill command scan |
| `tests/release-check.sh pre-tag\|post-tag` | Release check with the consumer denylist (`CCA_DENYLIST`), see README "Release" |
| `tests/test-run-on-server.sh` | cca-run-on-server config loading, logging, --create-file (fake ssh/tmux) |
| `tests/test-curl-secret.sh` | cca-curl-secret with fake sops/curl |
| `tests/test-command-safety.sh` | Test command safety validation |
| `tests/test-tmux-cli-script.sh` | Test literal multiline script execution with fake tmux |
| `tests/test-signal-handling.sh` | cca-tmux-cli exit codes and Ctrl-C/SIGTERM markers (private tmux server, skips without tmux) |
| `tests/test-shared-clean.sh` | Check repo has no project-specific names (run from project dir) |

## Key Files

- `bin/cca-install` - Installation helper (symlinks, not copies)
- `bin/cca-run-on-server` - Core infrastructure script
- `bin/cca-tmux-cli` - Tmux session management with agent-friendly commands (--robot-init, --doctor, --robot-help)

## Project Conventions
- ⛔ **project-agnostic: NEVER commit project-specific identifiers here** — concrete server names,
  client domains, internal tool names. This repo is shared across projects and public. Project values
  belong in the PROJECT `.cca-env` (legacy `.env`) as `CCA_*` vars read with a generic fallback (see `CCA_OUR_IPS`,
  `CCA_HOSTING_MARKER`, `CCA_APACHE_STATUS_CMD`, `CCA_NET_IFACE_PREFIXES`). Examples in docs and
  `--help` use `server1`, `server2`, `example.com`. This applies to tests too — a test fixture is
  not an exception.
  Guard: `tests/test-shared-clean.sh` (wraps `cca-check-shared-clean`, plus `tests/leak_scan.py`
  for backlog/ and src/) scans this repo against a denylist the PROJECT supplies via
  `$CCA_DENYLIST` or its cwd. **The project denylist never lives here** — storing it would leak
  the very names it guards; `tests/fixtures/leak-denylist.txt` only exercises the mechanism.
- ⛔ **developing this tool never uses anything from consumer projects' production** — no servers,
  APIs, secrets, configs or server names, not even read-only or temporarily (no temp configs in
  `tmp/`). Live use belongs to the project's own agent. Verify with tests, fixtures and public
  targets only. The only exception is the release check's `$CCA_DENYLIST` file.
- naming: new bin scripts and skills use `cca-` prefix; never rename a shipped script or skill without explicit approval (project docs and reports reference them, e.g. `asn-wrap` stays unprefixed)
- naming: user's explicit choice overrides conventions (e.g., `commit` not `committing`)
- project tracking: dependent projects are documented only in each project's own
  `.claude/CLAUDE.md`; never list project names or paths in this shared repo
- skills: use `skill-name/SKILL.md` directory format with YAML frontmatter (`name` + `description` minimum)
- skills: point to `--help` when possible, minimize doc duplication
- installation: symlinks via `cca-install`, never copies; target dirs must already exist
- git: concise commit messages, no verbose changelogs
- safety: always ask before filesystem-modifying commands (install, symlink, mkdir)
- security: use `cca-curl-secret` for API auth, never raw env vars
- cross-platform: solutions must work on Linux/macOS/Windows without extra dependencies
- tmp/: work-in-progress files (gitignored)

## Gotchas

- Some bin scripts still have internal references using old (unprefixed) names - audit in progress
- ⛔ **Scripts must resolve PROJECT data from the CWD, never relative to `Path(__file__)`** — they are
  installed as symlinks in PATH and shared across projects, so a script-relative path silently reads
  the wrong project's data (or none). Order: `$CCA_*` var → `./cca/<thing>` → `./<thing>`, and exit
  non-zero when nothing is found. An empty result reads as "nothing to do" and hides the bug for
  months (`cca-watchlist`, `cca-diagnose-gather`, `cca-learn-analyzer` all had it).
- `cca-install` errors if target directory doesn't exist (by design, won't auto-create)
- ⛔ **Config loading (`lib/cca-env.sh`, loader in `cca-tmux-cli`) is load-bearing**: projects contain nested
  git repos that inherit the parent project's `.cca-env`, and config files use CWD-relative paths. Never
  change the search walk, priority or stop condition; before any loader change compare HEAD vs new output
  in real consumer project dirs, including nested repos.
