---
id: TASK-1.3.7
title: Port cca-watchlist to cca watchlist
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 13:09'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Largest script (about 1600 lines); watchlist path currently from --watchlist, CCA_WATCHLIST or CWD files.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/cca-watchlist incl. add/edit validation; every row tested; path from .cca.toml or --watchlist
- [ ] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
