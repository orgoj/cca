---
id: TASK-1.2.1
title: Port open-ports
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 07:43'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.9
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of check-open-ports (nmap/nc/telnet/curl methods, optional delegate host) from the public-safe spec written in TASK-1.9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Targets and delegate hosts come from [servers] or validated CLI args; only the chosen method's executable is required
- [ ] #2 Release-ready: full pre-tag gate green incl. fixture denylist
- [ ] #3 Compatibility matrix derived from the TASK-1.9 spec; every row tested
<!-- AC:END -->
