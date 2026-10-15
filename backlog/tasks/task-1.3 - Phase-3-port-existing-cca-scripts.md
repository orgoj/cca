---
id: TASK-1.3
title: 'Phase 3: port existing cca-* scripts'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
curl, hetrix, check-domain, server-*, asn, diagnose and watchlist still read bash config and env; they move to subcommands with shared config and secrets. One release per subcommand; old scripts stay until consumers migrate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each listed script has a cca subcommand with a tested compatibility matrix
- [ ] #2 cca curl never puts a secret in curl argv, including {TOKEN} URL substitution
<!-- AC:END -->
