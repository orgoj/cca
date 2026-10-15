---
id: TASK-1.3
title: 'Phase 3: port existing cca-* scripts'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:44'
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
Existing cca-* scripts read bash config and env; they move to subcommands with shared config and secrets. One child task and release per subcommand; old scripts stay unchanged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All child tasks are Done
- [ ] #2 Each child is released: tag vX.Y.Z created after the consumer-denylist release check, post-tag version check passed, installed via uv tool install
<!-- AC:END -->
