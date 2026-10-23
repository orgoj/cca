---
id: TASK-10
title: >-
  Per-credential secrets validation: one invalid credential must not block
  unrelated requests
status: To Do
assignee: []
created_date: '2026-10-23 20:58'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reported by two consumer projects converting to cca 1.4.0: secrets.validate_curl validates every credential, so one invalid entry (e.g. missing origins or auth) makes cca curl and cca asn fail for all requests, including ones that never use that credential. Goal: an invalid credential blocks only requests that could use it. Open: whether cca doctor should report invalid credentials (doctor and config show never open secrets today, doc-2).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With one invalid credential in secrets.curl, cca curl to an origin of another valid credential succeeds and prints one warning naming the invalid credential's key path (never a value)
- [ ] #2 A request whose origin matches an invalid credential (or --cred-id naming it) exits 2 naming the key path; no other credential is silently chosen instead
- [ ] #3 cca asn without a matching ipapi.is credential runs keyless when other credentials are invalid
- [ ] #4 doc-2 secrets section and tests/fixtures/sops-shapes describe and cover the per-credential rule
<!-- AC:END -->
