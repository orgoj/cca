---
id: TASK-1.3.2
title: Port cca-hetrix to cca hetrix
status: To Do
assignee: []
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 15:31'
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
- [ ] #1 cca hetrix options, output and exit codes (incl. exit 2 on API failure) specified and tested as new behavior
- [ ] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
