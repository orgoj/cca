---
id: TASK-6
title: 'Security review leftovers: check-domain address dedup, hetrix regex anchor'
status: To Do
assignee: []
created_date: '2026-10-16 05:43'
labels: []
dependencies: []
priority: low
type: enhancement
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Open INFO findings from the TASK-1.3.2 and TASK-1.3.3 security reviews (tmp/review-task-1-3-3-security.md, gitignored). Hardening only, no current vulnerability.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 check_domain lookup() returns each address once, order preserved; a test with duplicate A records connects to the address once
- [ ] #2 hetrix MONITOR_ID_RE is anchored (^...$) and existing tests pass
<!-- AC:END -->
