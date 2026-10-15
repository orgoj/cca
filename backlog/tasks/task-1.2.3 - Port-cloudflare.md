---
id: TASK-1.2.3
title: Port cloudflare
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 14:49'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.9
references:
  - doc-5
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
- [x] #1 Token only from the configured sops file; SDK ambient credential/endpoint fallback disabled; test with a hostile CLOUDFLARE_API_TOKEN in env and missing project secret fails closed
- [x] #2 Write operations default to plan and change nothing without --apply
- [x] #3 Exports go to the doc-2 configured path
- [x] #4 Compatibility matrix derived from the TASK-1.9 spec; every row tested with an injected fake client
- [x] #5 tests/run-all.sh green incl. fixture denylist (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca cloudflare on the official SDK (cloudflare>=5.9,<6): token only from sops with every ambient SDK fallback neutralized, explicit pagination, 64 MiB / 60 s response limits never retried, ids in request paths validated, API strings escaped; writes plan by default, WAF writes snapshot to cloudflare.export_dir (doc-2 names) and read back. Compatibility matrix in doc-5, every row tested in tests/test_cca_cloudflare.py.
<!-- SECTION:FINAL_SUMMARY:END -->
