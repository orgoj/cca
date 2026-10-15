---
id: TASK-1.3.1
title: Port cca-curl-secret to cca curl
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca-curl-secret puts {TOKEN} URL substitutions in curl argv (visible in the process list) and picks credentials only from the first URL plus hostname fallback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/cca-curl-secret; every row tested
- [ ] #2 Request policy from doc-1 enforced: allowed origins per credential, HTTPS only, extra URLs rejected, no cross-origin redirect credential forwarding, header-printing options rejected with a credential, config values escaped and control characters rejected
- [ ] #3 Tests prove the secret is absent from curl argv and CCA diagnostics, incl. {TOKEN} URLs
- [ ] #4 Skills referencing cca-curl-secret updated in the same release; released as its own tag
<!-- AC:END -->
