---
id: TASK-1.11
title: Release complete cca (phases 2-4)
status: To Do
assignee: []
created_date: '2026-10-15 07:43'
updated_date: '2026-10-15 13:08'
labels: []
dependencies:
  - TASK-1.4
  - TASK-1.10
  - TASK-1.2
  - TASK-1.3
parent_task_id: TASK-1
priority: medium
type: chore
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No release per subcommand (user decision): the ports (TASK-1.2, TASK-1.3) and cca run (TASK-1.4) close when tests/run-all.sh is green; the complete cca is released once, here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Consumer-denylist release check passed
- [ ] #2 Tag vX.Y.Z created, post-tag version check passed
- [ ] #3 Installed via uv tool install from the tag; every subcommand in the doc-1 inventory runs from the installed tool
<!-- AC:END -->
