---
id: TASK-1.2.3
title: Port cloudflare
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of an Ansible project's cloudflare-cli (cloudflare SDK; DNS, WAF/rulesets, zone audit, exports). Source reads a plaintext token from env/.env files and bootstraps a project venv. Source is outside this repo; the porter reads it from the user's consumer project.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Public-safe behavior spec with compatibility matrix in backlog/docs; every row tested with an injected fake client
- [ ] #2 Token only from the configured sops file; SDK ambient credential/endpoint fallback disabled; test with a hostile CLOUDFLARE_API_TOKEN in env and missing project secret fails closed
- [ ] #3 Write operations default to plan and change nothing without --apply
- [ ] #4 Exports go to the doc-2 configured path
- [ ] #5 Released as its own tag after the consumer denylist check
<!-- AC:END -->
