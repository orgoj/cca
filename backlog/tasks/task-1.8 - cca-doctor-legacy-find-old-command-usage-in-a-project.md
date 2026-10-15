---
id: TASK-1.8
title: 'cca doctor --legacy: find old command usage in a project'
status: To Do
assignee: []
created_date: '2026-10-15 07:35'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Old cca-* commands are removed once consumers migrate. On each deployment the consumer projects must be checked for remaining references (scripts, Makefiles, CI, docs, skills, agent instructions), otherwise removal breaks them silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 cca doctor --legacy lists every reference to a retired command in the CWD project with file and line, exits non-zero when any is found
- [ ] #2 The list of retired commands ships with cca and grows with each port release
- [ ] #3 The deployment steps in README require running it in every consumer project after installing a release
<!-- AC:END -->
