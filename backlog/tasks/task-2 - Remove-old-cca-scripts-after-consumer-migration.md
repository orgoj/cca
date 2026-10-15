---
id: TASK-2
title: Remove old cca-* scripts after consumer migration
status: To Do
assignee: []
created_date: '2026-10-15 07:33'
updated_date: '2026-10-15 20:17'
labels:
  - 'blocked:external'
dependencies:
  - TASK-1
  - TASK-4
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
- [ ] #1 bin/, lib/cca-env.sh and root skills/ removed except an approved cca-tmux-cli wrapper; tests and docs updated
- [ ] #2 TASK-4 is done: every consumer project is converted and cca doctor passes there without any old CCA link finding (doc-6 step 8)
<!-- AC:END -->
