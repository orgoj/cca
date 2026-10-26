---
id: TASK-5
title: Release-check denylist covering all consumer projects
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 12:53'
updated_date: '2026-10-26 08:20'
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
- [x] #1 Every consumer project using cca has a denylist covering its servers, domains and internal tool names
- [x] #2 README Release documents how the release check runs against all consumer denylists
- [x] #3 Release check passes against every consumer denylist
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Release check now takes CCA_DENYLIST=FILE:FILE:... (one denylist per consumer project, each stays in its project); tests/leak_scan.py loads every file, fails on a missing file, an empty entry or a file without patterns; release-check.sh validates the list before running. README Release documents it (AC #2). Format/content spec for the projects handed to the coordination agent. Waiting for the four project denylists (AC #1) and a release check against all of them (AC #3).

All four consumer projects created their denylist (format spec handed out by the coordination agent). The first full scan found one real server name in two test files (replaced, dbc324b). Release check of v1.12.0 passed pre-tag and post-tag with CCA_DENYLIST listing all four. Commits are now guarded by githooks/pre-commit and commit-msg against the same list (git config cca.denylist).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Release check runs against every consumer denylist (FILE:FILE...); all four exist; v1.12.0 passed against all of them; commit hooks enforce the same list.
<!-- SECTION:FINAL_SUMMARY:END -->
