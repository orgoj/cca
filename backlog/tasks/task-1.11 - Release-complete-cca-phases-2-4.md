---
id: TASK-1.11
title: Release complete cca (phases 2-4)
status: Done
assignee: []
created_date: '2026-10-15 07:43'
updated_date: '2026-10-15 20:06'
labels: []
dependencies:
  - TASK-1.2
  - TASK-1.3
  - TASK-1.4
  - TASK-1.10
  - TASK-1.12
parent_task_id: TASK-1
priority: medium
type: chore
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No release per subcommand (user decision): the ports (TASK-1.2, TASK-1.3) and cca run (TASK-1.4) close when tests/run-all.sh is green; the complete cca is released once, here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Consumer-denylist release check passed
- [x] #2 Tag vX.Y.Z created, post-tag version check passed
- [x] #3 Installed via uv tool install from the tag; every subcommand in the doc-1 inventory runs from the installed tool
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Released v1.0.0 at bc530a7: release-check.sh pre-tag and post-tag passed with the consumer denylist; installed via uv tool install from git+file@v1.0.0, cca --version prints cca 1.0.0; every inventory subcommand answers --help, config show/doctor/run --list on a test fixture, check-domain/asn on public targets, open-ports on 127.0.0.1. No live calls to project servers or APIs (development rule).
<!-- SECTION:FINAL_SUMMARY:END -->
