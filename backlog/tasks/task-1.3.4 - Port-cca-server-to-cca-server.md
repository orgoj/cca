---
id: TASK-1.3.4
title: Port cca-server-* to cca server
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 18:59'
labels: []
dependencies:
  - TASK-1.4
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca-server-info, cca-server-status and cca-server-hostname are one family (server introspection) and read CCA_* variables such as status commands and interface prefixes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca server info|status|hostname options, output and exit codes specified and tested as new behavior; CCA_* inputs from doc-2 keys
- [x] #2 Remote commands go through the cca run executor API, no own ssh/subprocess code
- [x] #3 server info|status|hostname accept --all (every [servers] entry in config order, stop on first failure), replacing cca-run-all for them
- [x] #4 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Plan: one ssh call per section via executor.execute(via=ssh); XML-like tags; status = quick state, info = inventory; --all in config order stopping on first failure; total --timeout per server. User decisions recorded in doc-1 with the work commit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User decisions: run.transport only for live cca run, finished scripts (server, diagnose) always ssh via executor via="ssh" (doc-1, doc-2); one ssh call per section; XML-like tags; status/info without overlap, Firebird count dropped. Spec in doc-1 "cca server".
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added cca server hostname|status|info (SERVER or --all, total --timeout, exit attr per failed section, 255 stops the server) over executor.execute(via="ssh"); reference, SKILL.md, README, doc-1/doc-2. Verified with tests/test_cca_server.py (fake ssh + fake remote tools), section commands run locally against real tools, tests/run-all.sh ALL PASSED (739 pytest).
<!-- SECTION:FINAL_SUMMARY:END -->
