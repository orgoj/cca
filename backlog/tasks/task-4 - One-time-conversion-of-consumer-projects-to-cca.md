---
id: TASK-4
title: One-time conversion of consumer projects to cca
status: Done
assignee: []
created_date: '2026-10-15 12:21'
updated_date: '2026-10-26 07:18'
labels:
  - 'blocked:external'
dependencies:
  - TASK-1
priority: low
type: chore
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Starts only after the complete cca CLI is finished, reviewed and approved by the user. Converts each consumer project once by hand following the migration guide (doc-6): writes .cca.toml from its legacy input mapping, moves secrets into sops files, replaces old skill links with cca install skills, switches scripts, Makefiles, CI, docs, skills and agent instructions to cca subcommands, converts watchlist.json into Backlog.md tasks with cca watchlist migrate (doc-6 step 4: dry run, --apply, verifying rerun; the project's Backlog.md gets the statuses Idea and Note), and removes legacy config files (.cca-env, .env CCA_* keys, .cca-tmux-cli, .tmux-cli-python.yaml, .netdata-servers, watchlist.json). Every old cca-* skill link is removed; the packaged skill cca replaces them all (user decision, doc-6 "Skills").
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each consumer project has a valid .cca.toml and no remaining reference to an old cca-* command or legacy config input
- [x] #2 cca doctor passes in each consumer project
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
All consumer projects are converted (per the user the last project was the final one; its project agent confirmed via the coordination agent): valid .cca.toml, no legacy config inputs, no old cca-* references except history lines; cca doctor exit 0. Its only doctor WARN: shared user-level ~/bin links into the old bin/, removed with TASK-2 (doc-6 step 8).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every consumer project converted per doc-6; both criteria confirmed by the project agents (doctor exit 0). Legacy removal continues in TASK-2.
<!-- SECTION:FINAL_SUMMARY:END -->
