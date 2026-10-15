---
id: TASK-1.10
title: Release core (phase 1 + doctor --legacy)
status: To Do
assignee: []
created_date: '2026-10-15 07:43'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.8
parent_task_id: TASK-1
priority: high
type: chore
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port and core tasks close when release-ready; the actual tag and install need their own task because a task is closed in its implementation commit, before the tag exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Consumer-denylist release check passed
- [ ] #2 Tag vX.Y.Z created, post-tag version check passed
- [ ] #3 Installed via uv tool install from the tag; cca --version shows it
<!-- AC:END -->
