---
id: TASK-1.3.5
title: Port asn-wrap to cca asn
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
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every script to a cca subcommand; asn-wrap is the one unprefixed shipped script.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrix vs bin/asn-wrap; every row tested
- [ ] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
