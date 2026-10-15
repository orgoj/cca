---
id: TASK-1.3.2
title: Port cca-hetrix to cca hetrix
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.3.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca-hetrix calls cca-curl-secret and mentions an env API key; it must use cca curl internals and the sops file only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/cca-hetrix (incl. exit 2 on API failure); every row tested
- [ ] #2 Skills referencing cca-hetrix updated in the same release; released as its own tag
<!-- AC:END -->
