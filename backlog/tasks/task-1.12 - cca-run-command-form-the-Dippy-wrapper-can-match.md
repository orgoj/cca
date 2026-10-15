---
id: TASK-1.12
title: 'cca run: command form the Dippy wrapper can match'
status: Done
assignee: []
created_date: '2026-10-15 19:43'
updated_date: '2026-10-15 19:59'
labels: []
dependencies:
  - TASK-1.4
parent_task_id: TASK-1
priority: high
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dippy matches a wrapper by its command prefix, takes the server from an option value before the inner command and the inner command right after a trigger option (or one quoted heredoc after a script option). The current form cca run [opts] SERVER [-- CMD] does not fit. User decision: no separate tool; Dippy learns the wrapper cca run, cca adapts the rest to what Dippy matches. Final form agreed with Dippy before implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca run takes the server and the command in a form the Dippy wrapper cca run matches (agreed with Dippy, recorded in doc-1 cca run)
- [x] #2 --help, skill reference, README and tests use only the new form
- [x] #3 tests/run-all.sh green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca run takes the server as -t SERVER; the command after -- or a quoted heredoc on stdin; --all instead of -t; other surfaces keep a positional SERVER and exit 2 with -t or -- CMD. Contract agreed with Dippy (wrapper cca, subcommand run), recorded in doc-1.
<!-- SECTION:FINAL_SUMMARY:END -->
