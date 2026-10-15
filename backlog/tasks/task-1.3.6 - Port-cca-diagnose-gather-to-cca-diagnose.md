---
id: TASK-1.3.6
title: Port cca-diagnose-gather to cca diagnose
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 13:09'
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
- [ ] #1 Compatibility matrix vs bin/cca-diagnose-gather; every row tested; data paths from .cca.toml
- [ ] #2 Remote commands go through the cca run executor API, no own ssh/subprocess code
- [ ] #3 diagnose accepts --all (every [servers] entry in config order, stop on first failure), replacing cca-run-all for it
- [ ] #4 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
