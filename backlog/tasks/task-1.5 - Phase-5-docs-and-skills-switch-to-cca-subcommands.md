---
id: TASK-1.5
title: 'Phase 5: global docs and migration guide'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:43'
labels: []
dependencies:
  - TASK-1.2
  - TASK-1.3
  - TASK-1.11
parent_task_id: TASK-1
priority: low
type: docs
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After all ports are released, global docs must describe the cca CLI and give consumers a migration path. Skills are updated with each port; this task is the global cleanup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AGENTS.md, CLAUDE.md and README describe the cca CLI, install and release
- [ ] #2 A migration guide maps every legacy input from doc-2 to its .cca.toml key or states it was dropped
- [ ] #3 No file under bin/ or lib/ is modified by this task
<!-- AC:END -->
