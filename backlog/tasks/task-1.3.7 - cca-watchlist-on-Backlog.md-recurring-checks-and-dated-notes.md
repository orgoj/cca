---
id: TASK-1.3.7
title: 'cca watchlist on Backlog.md: recurring checks and dated notes'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 17:56'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The work register is the project's Backlog.md (backlog CLI, run in the config dir); cca watchlist adds only what Backlog lacks. Conventions: a recurring check is a task with label every:Nd whose due date is the next check, optional until:YYYY-MM-DD ends it; a note is a task in status Note with optional from:/until: labels (inclusive local dates). Subcommands: today (due tasks and notes valid today), notes --on DATE (notes valid on a date, e.g. during an outage), checked ID (moves the due date by the interval and comments, closes after until:). Everything else (refs, priority, dependencies, search, done) is plain Backlog.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca watchlist today, notes and checked: options, output and exit codes specified and tested as new behavior; backlog called only through its CLI with JSON output, malformed every:/from:/until: labels reported
- [x] #2 cca doctor FAIL when the backlog CLI is missing or the project's statuses lack Note
- [x] #3 watchlist.file removed from doc-2 and config; doc-1 describes the Backlog.md conventions; TASK-4 converts watchlist.json items to Backlog tasks
- [x] #4 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca watchlist today/notes/checked over the backlog CLI (JSON only, config dir, BACKLOG_* scrubbed); conventions in doc-1 "Watchlist on Backlog.md"; cca doctor checks backlog and the Note/Done statuses; watchlist.file removed from doc-2 and config; TASK-4 converts watchlist.json.
<!-- SECTION:FINAL_SUMMARY:END -->
