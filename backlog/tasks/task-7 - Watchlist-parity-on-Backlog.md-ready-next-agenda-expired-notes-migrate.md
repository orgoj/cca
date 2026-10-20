---
id: TASK-7
title: 'Watchlist parity on Backlog.md: ready, next, agenda, expired notes, migrate'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-20 12:23'
updated_date: '2026-10-20 12:30'
labels: []
dependencies: []
priority: medium
type: feature
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Supply the legacy cca-watchlist functions Backlog.md lacks (gap analysis in the reviewed proposal): today Priority section (legacy agenda), ready and next by effort/window/change-risk labels with Backlog dependency readiness, notes --expired, idle/standby labels outside the daily check, next action = Implementation Plan, and a one-shot cca watchlist migrate of a schema v2 watchlist.json with full preflight and idempotent rerun.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 ready, next, notes --expired and the today Priority section specified in --help, doc-1 and the skill reference and tested over the fake backlog
- [x] #2 migrate validates every item before the first write, maps per doc-1, is idempotent via watchlist:<id> and is tested incl. a mid-apply failure and a real-backlog run
- [x] #3 doc-6 step 4 and commands table, TASK-4, README updated; tests/run-all.sh and tests/test-shared-clean.sh green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca watchlist today Priority section, ready, next, notes --expired, idle/standby labels outside Due, plan = next action; cca watchlist migrate with full preflight, one-to-one watchlist:<id> idempotency, local-zone dates; doc-1, doc-6, TASK-4, README, skill reference updated. Plan and result reviewed by agent_review; tests/run-all.sh green.
<!-- SECTION:FINAL_SUMMARY:END -->
