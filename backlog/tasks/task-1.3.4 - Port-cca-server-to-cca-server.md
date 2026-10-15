---
id: TASK-1.3.4
title: Port cca-server-* to cca server
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 07:37'
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
- [ ] #1 cca server info|status|hostname with a compatibility matrix vs the three scripts; every row tested; CCA_* inputs from doc-2 keys
- [ ] #2 Skills referencing cca-server-* updated in the same change; release-ready: full pre-tag gate green
- [ ] #3 Remote commands go through the cca run executor API, no own ssh/subprocess code
- [ ] #4 server info|status|hostname accept --all (every [servers] entry in config order, stop on first failure), replacing cca-run-all for them
<!-- AC:END -->
