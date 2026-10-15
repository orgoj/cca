---
id: TASK-1.3.6
title: Port cca-diagnose-gather to cca diagnose
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every cca-* script to a cca subcommand; it historically resolved data relative to its own path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/cca-diagnose-gather; every row tested; data paths from .cca.toml
- [ ] #2 Skills referencing it updated in the same release; released as its own tag
<!-- AC:END -->
