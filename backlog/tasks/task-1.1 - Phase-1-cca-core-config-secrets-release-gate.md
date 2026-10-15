---
id: TASK-1.1
title: 'Phase 1: cca core, config, secrets, release gate'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:32'
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
- [ ] #1 Root pyproject.toml defines project cca with entry point cca; tmux_cli_python with its deps and tests stays packaged and green, only its entry point is removed; uv.lock and ruff target updated
- [ ] #2 Config loader implements doc-2: fixtures pass, higher schema_version exits 2, unknown keys warn, malformed nearest file exits 2
- [ ] #3 Discovery tests pass for exact CWD, descendant, nested shadow, none found, malformed nearest, filesystem root and symlinked CWD (physical path)
- [ ] #4 Secrets module decrypts via sops JSON; tests prove the secret is absent from CCA-generated argv, logs and diagnostics
- [ ] #5 cca --version, config show, doctor [--fix] and install skills [NAME] work from a wheel install without a source checkout
- [ ] #6 install skills replaces only links it owns, never overwrites or follows other skills, is idempotent and links stay valid after reinstall; fails clearly without symlink support
- [ ] #7 tests/run-all.sh runs pytest, ruff, uv build, wheel/sdist content check and install smoke into a temporary tool dir
- [ ] #8 Release step fails closed without the consumer denylist; automated gate uses a repository fixture denylist
- [ ] #9 README documents the verified uv tool install command and the release steps (pre-tag and post-tag checks)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review: the root pyproject change breaks any editable tmux-cli-python install; uninstall it on machines that have it when this lands. Current tests/run-all.sh installs the root project; adapt it in the same change.
<!-- SECTION:NOTES:END -->
