---
id: TASK-1.3.1
title: Port cca-curl-secret to cca curl
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 07:35'
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
- [ ] #2 Skills referencing cca-curl-secret updated in the same release; released as its own tag
- [ ] #3 Request policy from doc-1 enforced: allowed origin = scheme + normalized host + effective port, HTTPS only, every URL form (positional, --url, globbing, config file) checked and a second URL rejected, ambient .curlrc disabled, -K/--config, --write-out, -v, --trace*, --libcurl rejected with a credential, no cross-origin redirect credential forwarding, config values escaped and control characters rejected; each a negative test
- [ ] #4 Configured secrets are absent from curl argv and CCA diagnostics and redacted from curl stdout, stderr and error paths; tests incl. {TOKEN} URLs and a reflected-token fixture
<!-- AC:END -->
