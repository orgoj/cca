---
id: TASK-1.1
title: 'Phase 1: cca core, config, secrets, release gate'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 09:33'
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
Every later port depends on a stable config contract (doc-2), one secrets path and a release/install flow that never affects running agents. See doc-1 sections Config, Secrets, Layout, Release gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Config loader implements doc-2: fixtures pass, higher schema_version exits 2, unknown keys warn, malformed nearest file exits 2
- [ ] #2 Discovery tests pass for exact CWD, descendant, nested shadow, none found, malformed nearest, filesystem root and symlinked CWD (physical path)
- [ ] #3 Secrets module decrypts via sops JSON; tests prove the secret is absent from CCA-generated argv, logs and diagnostics
- [ ] #4 cca --version, config show, doctor [--fix] and install skills [NAME] work from a wheel install without a source checkout
- [ ] #5 install skills replaces only links it owns, never overwrites or follows other skills, is idempotent and links stay valid after reinstall; fails clearly without symlink support
- [ ] #6 tests/run-all.sh runs pytest, ruff, uv build, wheel/sdist content check and install smoke into a temporary tool dir
- [ ] #7 Release step fails closed without the consumer denylist; automated gate uses a repository fixture denylist
- [ ] #8 README documents the verified uv tool install command and the release steps (pre-tag and post-tag checks)
- [ ] #9 Root pyproject.toml defines project cca with entry point cca; tmux_cli_python/, its tests, entry point and deps (typer, pyyaml, libtmux) removed; uv.lock and ruff target updated; remaining tests green
- [ ] #10 Shared ssh helper: target only from [servers] or validated input, argv-only, used by every subcommand that calls ssh
- [ ] #11 The wheel ships src/cca/skills/ only; a wheel-install test scans installed skills and fails on any reference to a command not provided, incl. old cca-* names; root skills/ untouched
- [ ] #12 A legacy-baseline tag marks the pre-refactor state; tests/run-all.sh fails when bin/, lib/ or root skills/ differ from it
- [ ] #13 Repo leak check covers backlog/ and src/ as well (without changing bin/); the existing generic 'gate' wording in backlog/ is resolved (reworded or denylist pattern narrowed by the consumer project) so the check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review: the root pyproject change breaks any editable tmux-cli-python install; uninstall it on machines that have it when this lands. Current tests/run-all.sh installs the root project; adapt it in the same change.

Found in TASK-1.9: cca-check-shared-clean scans only bin, lib, skills, tests, tmux_cli_python and root md files, so backlog/ and src/ were never leak-checked. A direct scan of backlog/ with the consumer denylist only hits the generic word 'gate' (release gate, pre-tag gate).
<!-- SECTION:NOTES:END -->
