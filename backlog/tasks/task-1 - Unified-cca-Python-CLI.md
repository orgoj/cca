---
id: TASK-1
title: Unified cca Python CLI
status: To Do
assignee: []
created_date: '2026-10-15 07:12'
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
- [ ] #1 All subcommands in the doc-1 inventory are released and installable via uv tool install from a tag
- [ ] #2 No cca subcommand reads configuration other than .cca.toml or any environment variable
<!-- AC:END -->
