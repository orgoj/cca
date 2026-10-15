---
id: TASK-1.4
title: 'Phase 4: cca run'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 15:32'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Python successor of cca-tmux-cli, cca-run-on-server and cca-run-all; the bash scripts are the behavioral reference (tmux_cli_python was removed in phase 1 and its hook/audit pipeline is not carried over). The command shape is a public contract for external validators (Dippy); see doc-1 cca run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 cca run surfaces specified and tested as new behavior: robot-init, doctor, robot-help, list, read, session, exit codes, Ctrl-C/SIGTERM markers, logging, tokf, --list, --create-file, --all
- [ ] #2 cca run SERVER -- CMD and cca run SERVER with CMD on stdin work over tmux and ssh; no CMD with TTY stdin or empty stdin exits non-zero
- [ ] #3 Surfaces meaningless for a transport (e.g. read over ssh) exit non-zero with a clear error
- [ ] #4 SERVER only from [servers]; ssh target validated and passed as separate argv
- [ ] #5 No local shell is used to build tmux or ssh calls; tests with malicious server names and commands show no local shell execution on both transports
- [ ] #6 Execution is a reusable executor API (server, command, transport) that other subcommands call; cca run is a thin CLI over it
- [ ] #7 cca run --all -- CMD (and stdin) runs CMD on every [servers] entry in config order, output tagged per server, stops on the first failure; tests cover order and stop-on-failure
- [ ] #8 New cca skills for cca run added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->
