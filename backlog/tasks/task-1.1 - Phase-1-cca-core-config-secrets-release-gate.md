---
id: TASK-1.1
title: 'Phase 1: cca core, config, secrets, release gate'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:17'
labels: []
dependencies: []
parent_task_id: TASK-1
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every later port depends on a stable config contract, one secrets path and a release/install flow that never affects running agents. See doc-1 sections Config, Secrets, Layout, Release gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Root pyproject.toml defines project cca with entry point cca; tmux-cli-python entry point removed
- [ ] #2 .cca.toml schema v1 covers every configurable value of all inventoried tools; unknown keys and malformed files exit 2
- [ ] #3 Discovery tests pass for exact CWD, descendant, nested shadow, none found, malformed nearest, filesystem root
- [ ] #4 Secrets module decrypts via sops JSON and tests prove the secret never appears in child argv or output
- [ ] #5 cca --version, cca config show, cca doctor and cca install skills work from a wheel install without a source checkout
- [ ] #6 tests/run-all.sh runs pytest, ruff, uv build, wheel-content check and install smoke into a temporary tool dir
- [ ] #7 Schema v1 includes every value listed in doc-1 Config inventory, checked by a test against the doc list
- [ ] #8 README documents the verified uv tool install command and the release steps
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review: the root pyproject change breaks any editable tmux-cli-python install; uninstall it on machines that have it when this lands. Current tests/run-all.sh installs the root project; adapt it in the same change.
<!-- SECTION:NOTES:END -->
