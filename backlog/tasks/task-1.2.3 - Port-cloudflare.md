---
id: TASK-1.2.3
title: Port cloudflare
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
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of cloudflare-cli (cloudflare SDK; DNS, WAF/rulesets, zone audit, exports) from the public-safe spec written in TASK-1.9. The source read a plaintext token from env/.env files and bootstrapped a project venv.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Token only from the configured sops file; SDK ambient credential/endpoint fallback disabled; test with a hostile CLOUDFLARE_API_TOKEN in env and missing project secret fails closed
- [ ] #2 Write operations default to plan and change nothing without --apply
- [ ] #3 Exports go to the doc-2 configured path
- [ ] #4 Release-ready: full pre-tag gate green incl. fixture denylist
- [ ] #5 Compatibility matrix derived from the TASK-1.9 spec; every row tested with an injected fake client
<!-- AC:END -->
