---
id: TASK-1.10
title: Release core (phase 1 + doctor link check)
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:43'
updated_date: '2026-10-15 12:53'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.8
parent_task_id: TASK-1
priority: high
type: chore
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port and core tasks close when release-ready; the actual tag and install need their own task because a task is closed in its implementation commit, before the tag exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Consumer-denylist release check passed
- [x] #2 Tag vX.Y.Z created, post-tag version check passed
- [x] #3 Installed via uv tool install from the tag; cca --version shows it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Released v0.1.0 (no version bump, first tag) at e76cb43: release-check.sh pre-tag and post-tag passed with the consumer denylist; installed via uv tool install from git+file@v0.1.0, cca --version prints cca 0.1.0. Follow-up TASK-5: denylist from all consumer projects.
<!-- SECTION:FINAL_SUMMARY:END -->
