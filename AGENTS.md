# CCA - Cyber-CLI Admin Toolkit

Agent-agnostic toolkit: one Python command `cca <subcommand>` (installed with uv) and its
skill `cca`. The old `cca-*` scripts and skills are gone (TASK-2); history: tag `legacy-baseline`.

## Architecture

```
src/cca/       # unified `cca` Python CLI (uv project at repo root)
  cli.py       # static COMMANDS registry, lazy import per subcommand
  commands/    # one module per subcommand
  skills/cca/  # the shipped skill: SKILL.md + references/<subcommand>.md
tests/         # bash tests, pytest (tests/test_cca_*.py), fixtures
backlog/       # Backlog.md tasks; docs/doc-1 design, doc-2 .cca.toml schema, doc-6 migration guide
```

## Commands

Run test scripts directly (they are executable), never as `bash tests/...`; new test scripts get `chmod +x`.

| Command | Description |
|---------|-------------|
| `uv run cca --help` | Run the CLI from the work tree |
| `uv run pytest tests/test_cca_<name>.py` | Tests of one subcommand |
| `uv run ruff check` / `uv run ruff format <file>` | Lint / format |
| `tests/run-all.sh` | Run everything: shellcheck, bash tests, ruff, pytest, package checks |
| `tests/test-leak-scan.sh` | backlog/ and src/ against the fixture denylist; release check fails closed |
| `tests/test-package.sh [DENYLIST]` | uv build, wheel/sdist content, install smoke into a temp uv tool dir, skill command scan |
| `tests/release-check.sh pre-tag\|post-tag` | Release check with the consumer denylist (`CCA_DENYLIST`), see README "Release" |
| `tests/test-shared-clean.sh` | Check repo has no project-specific names (run from project dir) |

Install and release: README "Install" and "Release" (non-editable `uv tool install` from a
tag; tags never move; subcommands are not released one by one).

## Key Files

- `src/cca/config.py` - `.cca.toml` discovery and validation (schema: doc-2)
- `src/cca/secrets.py` - sops secrets; `src/cca/validate.py` - escaping of remote/API strings
- `src/cca/executor.py` - command execution over tmux or ssh, `[run.log]` (used by `run`, `server`)
- `src/cca/skills/cca/` - every new subcommand adds `references/<sub>.md`, a SKILL.md row
  and a README "Subcommands" row; the package test flags any "`cca <word>`" in skills that
  is not a real command

## Project Conventions
- ⛔ **project-agnostic: NEVER commit project-specific identifiers here** — concrete server names,
  client domains, internal tool names. This repo is shared across projects and public. Project values
  belong in the PROJECT `.cca.toml` (doc-2), secrets in its sops files. Examples in docs and
  `--help` use `server1`, `server2`, `example.com`, `203.0.113.x`. This applies to tests too — a
  test fixture is not an exception.
  Guard: `tests/test-shared-clean.sh` (`tests/leak_scan.py` over every tracked file) scans
  this repo against a denylist the PROJECT supplies via
  `$CCA_DENYLIST` or its cwd. **The project denylist never lives here** — storing it would leak
  the very names it guards; `tests/fixtures/leak-denylist.txt` only exercises the mechanism.
  Commit guard: `githooks/pre-commit` (staged lines, file names) and `githooks/commit-msg`
  refuse a commit with a denylisted name. One-time per clone: `git config core.hooksPath
  githooks` and `git config cca.denylist FILE:FILE...` (every consumer denylist; local
  config, never committed). Never bypass them with `--no-verify`.
- ⛔ **developing this tool never uses anything from consumer projects' production** — no servers,
  APIs, secrets, configs or server names, not even read-only or temporarily (no temp configs in
  `tmp/`). Live use belongs to the project's own agent. Verify with tests, fixtures and public
  targets only. The only exception is the release check's `$CCA_DENYLIST` file.
- config: `cca` reads settings only from one `.cca.toml` and secrets only from sops, never from
  environment variables; a new setting is a doc-2 schema change
- skills: the only shipped skill is `cca` (`src/cca/skills/cca/`); a new topic is a reference
  there, not a new skill; never rename a subcommand without explicit approval (project docs
  and reports reference them)
- naming: user's explicit choice overrides conventions (e.g., `commit` not `committing`)
- project tracking: dependent projects are documented only in each project's own
  `.claude/CLAUDE.md`; never list project names or paths in this shared repo
- skills: use `skill-name/SKILL.md` directory format with YAML frontmatter (`name` + `description` minimum)
- skills: point to `--help` when possible, minimize doc duplication
- installation: `cca install skills` links skills, never copies; target dirs must already exist
- git: concise commit messages, no verbose changelogs
- reviews: every review finding not fixed in the reviewed change (any severity, incl. INFO)
  becomes a Backlog.md task, so it is not lost with the gitignored report
- safety: always ask before filesystem-modifying commands (install, symlink, mkdir)
- security: use `cca curl` for API auth, never raw env vars
- cross-platform: solutions must work on Linux/macOS/Windows without extra dependencies
- tmp/: work-in-progress files (gitignored)

## Gotchas

- ⛔ **Resolve PROJECT data from the project, never relative to `Path(__file__)`** — `cca` is
  installed once and shared across projects, so a script-relative path silently reads the wrong
  project's data (or none). `cca` resolves paths in `.cca.toml` from its directory and CLI paths
  from the CWD, and exits non-zero when something required is missing. An empty result reads as
  "nothing to do" and hides the bug for months (`cca-watchlist`, `cca-diagnose-gather`,
  `cca-learn-analyzer` all had it).
- `cca install skills` errors if the target directory doesn't exist (by design, won't auto-create)
- `pipefail` + a reader that exits before EOF (`head`, `grep -q`, a test fake that ignores
  stdin) kills the writer with SIGPIPE (exit 141): a flaky failure only under load. Test
  fakes fed through a pipe must read stdin (`cat >/dev/null`); don't pipe into early-exit
  readers under `pipefail`.
