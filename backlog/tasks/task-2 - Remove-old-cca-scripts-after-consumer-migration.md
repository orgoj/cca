---
id: TASK-2
title: Remove old cca-* scripts after consumer migration
status: To Do
assignee: []
created_date: '2026-10-15 07:33'
updated_date: '2026-10-15 09:05'
labels:
  - 'blocked:external'
dependencies:
  - TASK-1
  - TASK-1.8
priority: low
type: chore
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Old scripts and lib/cca-env.sh stay unchanged until every consumer project runs on cca subcommands; then they are deleted. Whether cca-tmux-cli stays as a thin wrapper over cca run is decided by the user then. Requires explicit user approval to start.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 cca doctor --legacy reports no references in every consumer project
- [ ] #2 bin/, lib/cca-env.sh and root skills/ removed except an approved cca-tmux-cli wrapper; tests and docs updated
<!-- AC:END -->
