---
id: TASK-1.2.2
title: Port netdata
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of an Ansible project's netdata-cli.py (stdlib; reads Netdata API directly or over ssh). Source resolves .netdata-servers relative to its own path and writes an fping cache under a project dir. Source is outside this repo; the porter reads it from the user's consumer project.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Public-safe behavior spec with compatibility matrix in backlog/docs; every row tested, incl. ssh vs direct transport and fping paths
- [ ] #2 Server addresses come from [servers] in .cca.toml; cache paths from doc-2 keys
- [ ] #3 Released as its own tag after the consumer denylist check
<!-- AC:END -->
