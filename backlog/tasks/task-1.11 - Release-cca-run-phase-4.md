---
id: TASK-1.11
title: Release cca run (phase 4)
status: To Do
assignee: []
created_date: '2026-10-15 07:43'
labels: []
dependencies:
  - TASK-1.4
parent_task_id: TASK-1
priority: medium
type: chore
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca run closes when release-ready; tagging and install are tracked here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Consumer-denylist release check passed
- [ ] #2 Tag vX.Y.Z created, post-tag version check passed
- [ ] #3 Installed via uv tool install from the tag; cca run works from the installed tool
<!-- AC:END -->
