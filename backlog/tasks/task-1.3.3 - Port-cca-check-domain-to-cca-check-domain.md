---
id: TASK-1.3.3
title: Port cca-check-domain to cca check-domain
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
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every cca-* script to a cca subcommand.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/cca-check-domain; every row tested; CCA_* inputs from doc-2 keys
- [ ] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
