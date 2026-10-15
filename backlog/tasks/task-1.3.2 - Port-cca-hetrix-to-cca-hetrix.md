---
id: TASK-1.3.2
title: Port cca-hetrix to cca hetrix
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 16:13'
labels: []
dependencies:
  - TASK-1.3.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca-hetrix calls cca-curl-secret and mentions an env API key; it must use cca curl internals and the sops file only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca hetrix options, output and exit codes (incl. exit 2 on API failure) specified and tested as new behavior
- [x] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
cca hetrix on HetrixTools API v3 (urllib, bearer credential for https://api.hetrixtools.com from secrets.curl). Subcommands status/down/all/response-times/outages/monitor-outages/monitor-info/server-stats/blacklist [TARGET]; server-stats uses v3 server-agent/metrics (v1 dropped); blacklist exit 1 except dnsbl-2/dnsbl-3.uceprotect.net (warning only). Behavior: src/cca/skills/cca/references/hetrix.md; tests: tests/test_cca_hetrix.py.
<!-- SECTION:NOTES:END -->
