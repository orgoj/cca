---
id: TASK-1.2
title: 'Phase 2: port open-ports, netdata, cloudflare'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:17'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: high
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three tools from an Ansible project's bin/ are generic and needed in non-Ansible projects; the sources resolve data relative to their own path and contain project-specific text. Source files are not in this repo; get them from the user.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each subcommand has a compatibility matrix with every row covered by a test
- [ ] #2 Server data comes from [servers] in .cca.toml, cloudflare token from the configured sops file
- [ ] #3 Sources sanitized; test-shared-clean passes against the consumer denylist before each release
- [ ] #4 cca cloudflare write operations default to plan and change nothing without --apply, covered by a test
- [ ] #5 Each subcommand is released as its own tagged version
<!-- AC:END -->
