---
id: TASK-1.3.5
title: Port asn-wrap to cca asn
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 17:12'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every script to a cca subcommand; asn-wrap is the one unprefixed shipped script.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca asn options, output and exit codes specified and tested as new behavior
- [x] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
cca asn: RIPEstat (prefix-overview, rpki-validation, abuse-contact-finder for --json), ipapi.is (optional key = curl credential for https://api.ipapi.is, POST body only; keyless otherwise), PTR via dnspython; non-global addresses not looked up. Key rule in doc-2 secrets.curl.
<!-- SECTION:NOTES:END -->
