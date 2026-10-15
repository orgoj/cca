---
id: TASK-1.3
title: 'Phase 3: port existing cca-* scripts'
status: Done
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 19:11'
labels: []
dependencies:
  - TASK-1.10
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Existing cca-* scripts read bash config and env; they move to subcommands with shared config and secrets. One child task per subcommand; released with the complete cca (TASK-1.11); old scripts stay unchanged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All child tasks are Done
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
All ported scripts are cca subcommands (curl, hetrix, check-domain, server, asn, watchlist); cca-diagnose-gather not ported (TASK-1.3.6).
<!-- SECTION:FINAL_SUMMARY:END -->
