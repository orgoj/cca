---
id: TASK-2
title: Remove old cca-* scripts after consumer migration
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:33'
updated_date: '2026-10-26 07:54'
labels: []
dependencies:
  - TASK-1
  - TASK-4
priority: low
type: chore
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Old scripts and lib/cca-env.sh stay unchanged until every consumer project runs on cca subcommands; then they are deleted. Whether cca-tmux-cli stays as a thin wrapper over cca run is decided by the user then. Requires explicit user approval to start.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bin/, lib/cca-env.sh and root skills/ removed except an approved cca-tmux-cli wrapper; tests and docs updated
- [x] #2 TASK-4 is done: every consumer project is converted and cca doctor passes there without any old CCA link finding (doc-6 step 8)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
No cca-tmux-cli wrapper: the user confirmed cca-tmux-cli is gone everywhere. Removed bin/, lib/, root skills/ and the legacy tests (test-run-on-server, test-curl-secret, test-command-safety, test-tmux-cli-script, test-signal-handling, test-hetrix, test-legacy-baseline, test_asn_wrap, test_watchlist). The repo leak check bin/cca-check-shared-clean is replaced by tests/leak_scan.py over every tracked file (wider: also backlog/, src/, .hcom/, root files); its generic example checks now cover cca run -t / cca check-domain in src/, README, AGENTS.md. The shared ~/bin links into bin/ were removed by agent bin before this change.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Legacy scripts, config loader and skills removed with their tests; docs (AGENTS.md, README) describe only cca; tests/run-all.sh ALL PASSED (867 pytest), shared-clean with the consumer denylist clean over all 178 tracked files.
<!-- SECTION:FINAL_SUMMARY:END -->
