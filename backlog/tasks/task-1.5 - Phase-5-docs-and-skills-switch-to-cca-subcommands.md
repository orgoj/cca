---
id: TASK-1.5
title: 'Phase 5: docs and skills switch to cca subcommands'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:17'
labels: []
dependencies:
  - TASK-1.2
  - TASK-1.3
  - TASK-1.4
parent_task_id: TASK-1
priority: low
type: docs
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After ports are released, docs and skills must point to cca <sub> so consumers migrate; old scripts get deprecation notes and are deleted only after all consumers converted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AGENTS.md, CLAUDE.md, README and skills reference cca subcommands
- [ ] #2 Old cca-* scripts are marked deprecated in docs and --help only; their runtime output is unchanged
- [ ] #3 A migration guide maps every old CCA_* variable and config file to its .cca.toml key
<!-- AC:END -->
