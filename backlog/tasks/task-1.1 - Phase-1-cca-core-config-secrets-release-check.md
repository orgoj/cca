---
id: TASK-1.1
title: 'Phase 1: cca core, config, secrets, release check'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 12:10'
labels: []
dependencies:
  - TASK-1.6
parent_task_id: TASK-1
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every later port depends on a stable config contract (doc-2), one secrets path and a release/install flow that never affects running agents. See doc-1 sections Config, Secrets, Layout, Release check and install.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Config loader implements doc-2: fixtures pass, higher schema_version exits 2, unknown keys warn, malformed nearest file exits 2
- [x] #2 Discovery tests pass for exact CWD, descendant, nested shadow, none found, malformed nearest, filesystem root and symlinked CWD (physical path)
- [x] #3 Secrets module decrypts via sops JSON; tests prove the secret is absent from CCA-generated argv, logs and diagnostics
- [x] #4 cca --version, config show, doctor [--fix] and install skills [NAME] work from a wheel install without a source checkout
- [x] #5 install skills replaces only links it owns, never overwrites or follows other skills, is idempotent and links stay valid after reinstall; fails clearly without symlink support
- [x] #6 tests/run-all.sh runs pytest, ruff, uv build, wheel/sdist content check and install smoke into a temporary tool dir
- [x] #7 Release step fails closed without the consumer denylist; automated check uses a repository fixture denylist
- [x] #8 README documents the verified uv tool install command and the release steps (pre-tag and post-tag checks)
- [x] #9 Root pyproject.toml defines project cca with entry point cca; tmux_cli_python/, its tests, entry point and deps (typer, pyyaml, libtmux) removed; uv.lock and ruff target updated; remaining tests green
- [x] #10 Shared ssh helper: target only from [servers] or validated input, argv-only, used by every subcommand that calls ssh
- [x] #11 The wheel ships src/cca/skills/ only; a wheel-install test scans installed skills and fails on any reference to a command not provided, incl. old cca-* names; root skills/ untouched
- [x] #12 A legacy-baseline tag marks the pre-refactor state; tests/run-all.sh fails when bin/, lib/ or root skills/ differ from it
- [x] #13 Repo leak check covers backlog/ and src/ as well (without changing bin/); the generic release-step wording in backlog/ that the consumer denylist flagged is reworded so the check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review: the root pyproject change breaks any editable tmux-cli-python install; uninstall it on machines that have it when this lands. Current tests/run-all.sh installs the root project; adapt it in the same change.

Found in TASK-1.9: cca-check-shared-clean scans only bin, lib, skills, tests, tmux_cli_python and root md files, so backlog/ and src/ were never leak-checked. A direct scan of backlog/ with the consumer denylist only hit one generic word in release-step wording; reworded to 'check' in TASK-1.1.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Root project switched to cca (src layout, Python >=3.11, entry point cca, lazy subcommand import); tmux_cli_python with its tests and deps removed. cca.config implements doc-2 (physical-CWD discovery, --config, load/use-time validation, unknown-key warnings, watchlist default) with config show. cca.secrets decrypts via sops JSON with fixed secret-free errors; cca.ssh builds argv-only calls with validated targets. install skills [NAME] [--target DIR] owns links via TARGET/.cca-skills.json or live links into a marked cca skills dir, rolls back on manifest failure; doctor [--fix] checks config, sops, cca dirs, run.log dir and skill links. The wheel ships one skill cca with per-subcommand references. run-all adds ruff, legacy-baseline check (tag at 90ce33e, incl. untracked/ignored files), leak scan of backlog/ and src/ with a fixture denylist, uv build + wheel/sdist content check + install smoke in a temp uv tool dir + installed-skill command scan; tests/release-check.sh pre-tag|post-tag requires the consumer denylist. README documents the verified uv tool install and release steps. Release-step wording in backlog reworded. doc-1: install skills uses --target DIR.
<!-- SECTION:FINAL_SUMMARY:END -->
