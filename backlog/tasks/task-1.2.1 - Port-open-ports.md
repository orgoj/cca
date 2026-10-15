---
id: TASK-1.2.1
title: Port open-ports
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of an Ansible project's check-open-ports (nmap/nc/telnet/curl methods, optional delegate host). Source is outside this repo; the porter reads it from the user's consumer project and records behavior in a public-safe spec.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Public-safe behavior spec with compatibility matrix in backlog/docs; every row tested
- [ ] #2 Targets and delegate hosts come from [servers] or validated CLI args; only the chosen method's executable is required
- [ ] #3 Released as its own tag after the consumer denylist check
<!-- AC:END -->
