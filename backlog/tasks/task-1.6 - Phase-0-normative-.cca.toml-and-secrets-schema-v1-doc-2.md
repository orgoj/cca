---
id: TASK-1.6
title: 'Phase 0: normative .cca.toml and secrets schema v1 (doc-2)'
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 09:07'
labels: []
dependencies:
  - TASK-1.9
parent_task_id: TASK-1
priority: high
type: docs
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The core config API is public contract; later ports must not change it silently. Old tools read many CCA_* variables and ad-hoc files (doc-1 Config lists them) whose new place must be fixed before implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog/docs doc-2 defines every table, key, type, default and validation rule of schema v1
- [ ] #2 doc-2 maps every legacy input listed in doc-1 Config to a .cca.toml key or marks it intentionally dropped
- [ ] #3 doc-2 defines the sops file shape for each secret-using command, incl. curl allowed origins and cloudflare api_token
- [ ] #4 Valid and invalid TOML fixtures for schema v1 exist under tests/fixtures/ for the core tests
- [ ] #5 doc-2 carries the cca curl request-policy fields (allowed origins with scheme, host, port) from doc-1
- [ ] #6 doc-2 defines the [legacy] table (include, allow) and the default exclusion list for cca doctor --legacy
- [ ] #7 doc-2 lists the agent skill install dirs probed by cca doctor --legacy
<!-- AC:END -->
