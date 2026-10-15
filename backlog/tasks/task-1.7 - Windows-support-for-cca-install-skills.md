---
id: TASK-1.7
title: Windows support for cca install skills
status: To Do
assignee: []
created_date: '2026-10-15 07:33'
labels:
  - deferred
dependencies: []
parent_task_id: TASK-1
priority: low
type: feature
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Windows without developer mode has no unprivileged symlinks; for now cca install skills fails there with a clear error. Deferred by user decision; do not start without approval.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 cca install skills works on Windows without symlink privileges, never following or overwriting skills it does not own
<!-- AC:END -->
