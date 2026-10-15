---
id: TASK-1.3.6
title: Do not port cca-diagnose-gather
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 19:11'
labels: []
dependencies:
  - TASK-1.4
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every cca-* script to a cca subcommand; it historically resolved data relative to its own path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca-diagnose-gather recorded as not ported in doc-1; no cca diagnose command
- [x] #2 [diagnose] removed from the .cca.toml schema (doc-2, config.py, fixtures); CCA_APACHE_STATUS_CMD/CCA_MONGODB_STATUS_CMD mapped as dropped
- [x] #3 Old script and skill cca-diagnosing stay until TASK-2; tests/run-all.sh green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
User decision: not ported, servers differ too much for fixed checks; agents use cca server status and cca run. [diagnose] removed from the schema (doc-2, config.py, fixtures), legacy env vars mapped as dropped, doc-1 inventory records it as not ported.
<!-- SECTION:FINAL_SUMMARY:END -->
