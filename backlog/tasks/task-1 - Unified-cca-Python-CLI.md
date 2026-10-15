---
id: TASK-1
title: Unified cca Python CLI
status: Done
assignee: []
created_date: '2026-10-15 07:12'
updated_date: '2026-10-15 20:21'
labels: []
dependencies: []
priority: high
type: feature
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
CCA should be usable in any project, with or without Ansible, as one uv-installed command with subcommands instead of many cca-* scripts reading bash config. Design: backlog/docs/doc-1 (cca unified CLI design).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All subcommands in the doc-1 inventory are released and installable via uv tool install from a tag
- [x] #2 No cca subcommand reads configuration or secrets from anything but .cca.toml and the sops files it names
- [x] #3 bin/, lib/ and root skills/ are unchanged from the plan baseline until TASK-2, so running agents see no change before cca is finished and deployed
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
All subtasks Done (TASK-1.7 moved to TASK-3 as duplicate). #1: tag v1.0.0 (bc530a7) installed with uv tool install from git+file@v1.0.0; cca --help lists every doc-1 inventory subcommand; src/ and pyproject.toml unchanged since the tag. #2: config only via cca.config (.cca.toml), secrets only via sops; os.environ is used only to find old scripts (doctor) and as the scrubbed environment of child processes (curl runs with -q, watchlist drops BACKLOG_*); HTTP clients ignore proxy env. #3: tests/test-legacy-baseline.sh passes.
<!-- SECTION:FINAL_SUMMARY:END -->
