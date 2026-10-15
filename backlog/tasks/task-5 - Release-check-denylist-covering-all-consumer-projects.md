---
id: TASK-5
title: Release-check denylist covering all consumer projects
status: To Do
assignee: []
created_date: '2026-10-15 12:53'
labels: []
dependencies:
  - TASK-1.5
  - TASK-4
priority: low
type: chore
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The release check (CCA_DENYLIST) currently uses the denylist of one consumer project only. Once the complete cca is finished and the consumer projects are converted, collect the names to guard from every project that uses cca, so the public repo is checked against all of them. The denylists stay in the consumer projects, never in this repo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every consumer project using cca has a denylist covering its servers, domains and internal tool names
- [ ] #2 README Release documents how the release check runs against all consumer denylists
- [ ] #3 Release check passes against every consumer denylist
<!-- AC:END -->
