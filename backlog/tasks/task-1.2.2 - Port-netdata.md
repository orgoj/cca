---
id: TASK-1.2.2
title: Port netdata
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
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of netdata-cli.py (stdlib; Netdata API directly or over ssh; fping cache) from the public-safe spec written in TASK-1.9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Server addresses come from [servers] in .cca.toml; cache paths from doc-2 keys
- [ ] #2 Release-ready: full pre-tag gate green incl. fixture denylist
- [ ] #3 Compatibility matrix derived from the TASK-1.9 spec; every row tested, incl. ssh vs direct transport and fping paths
<!-- AC:END -->
