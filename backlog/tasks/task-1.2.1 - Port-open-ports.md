---
id: TASK-1.2.1
title: Port open-ports
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 13:09'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.9
references:
  - doc-3
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of check-open-ports (nmap/nc/curl methods, optional delegate server; legacy telnet method dropped) from the public-safe spec written in TASK-1.9 (doc-3).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Targets and delegate hosts come from [servers] or validated CLI args; only the chosen method's executable is required
- [x] #2 Compatibility matrix derived from the TASK-1.9 spec; every row tested
- [x] #3 tests/run-all.sh green incl. fixture denylist (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decisions (user): nc and curl probe every port, exit 1 when any failed; telnet dropped; .cca.toml loaded only with --delegate. Review: legacy duplicate ports kept; IPv6 zone ids rejected. Compatibility matrix: doc-3.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added cca open-ports (src/cca/commands/open_ports.py): nmap/nc/curl probes, -k/--kubernetes, -n/--noact, -d/--delegate SERVER from [servers] over cca.ssh (config loaded only then), validated HOST (no IPv6 zone id) and ports, lazy tool check naming the tool. User decisions: nc and curl probe every port and exit 1 on any failure, telnet dropped. Compatibility matrix in doc-3, every row tested in tests/test_cca_open_ports.py (51 tests, fake tools). Skill reference open-ports.md, SKILL.md and README rows. run-all ALL PASSED (fixture denylist leak scan, package + install smoke), shared-clean with consumer denylist clean; code and security reviews addressed. Released with the complete cca (TASK-1.11).
<!-- SECTION:FINAL_SUMMARY:END -->
