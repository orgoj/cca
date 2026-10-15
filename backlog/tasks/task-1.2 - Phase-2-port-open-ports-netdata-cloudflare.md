---
id: TASK-1.2
title: 'Phase 2: port open-ports, netdata, cloudflare'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:44'
labels: []
dependencies:
  - TASK-1.10
parent_task_id: TASK-1
priority: high
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three tools from an Ansible project's bin/ are generic and needed in non-Ansible projects; the sources resolve data relative to their own path and contain project-specific text. One child task and release per subcommand.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All child tasks are Done
- [ ] #2 Each child is released: tag vX.Y.Z created after the consumer-denylist release check, post-tag version check passed, installed via uv tool install
<!-- AC:END -->
