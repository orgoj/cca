---
id: TASK-1.4
title: 'Phase 4: cca run'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 18:28'
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
- [x] #1 cca run surfaces specified and tested as new behavior: run, --list, --read, --session, exit codes, Ctrl-C/SIGTERM markers, logging, tokf, --create-file, --all; the robot-init/doctor/robot-help checks of cca-tmux-cli are covered by cca doctor and cca run --help
- [x] #2 cca run SERVER -- CMD and cca run SERVER with CMD on stdin work over tmux and ssh; no CMD with TTY stdin or empty stdin exits non-zero
- [x] #3 Surfaces meaningless for a transport (e.g. read over ssh) exit non-zero with a clear error
- [x] #4 SERVER only from [servers]; ssh target validated and passed as separate argv
- [x] #5 No local shell is used to build tmux or ssh calls; tests with malicious server names and commands show no local shell execution on both transports
- [x] #6 Execution is a reusable executor API (server, command, transport) that other subcommands call; cca run is a thin CLI over it
- [x] #7 cca run --all -- CMD (and stdin) runs CMD on every [servers] entry in config order, output tagged per server, stops on the first failure; tests cover order and stop-on-failure
- [x] #8 New cca skills for cca run added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Executor (src/cca/executor.py) built on the tmux core of the former tmux_cli_python with direct tmux argv; thin CLI src/cca/commands/run.py; doctor run checks; run.tokf moved to [run]; tests/test_cca_run.py with fake ssh and a real tmux on a private socket; doc-1 cca run, doc-2 [run], skill reference run.md.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Code basis: tmux core of the former tmux_cli_python (git history before phase 1), libtmux replaced by direct tmux argv. Fixed vs predecessors: send-keys argument limit (~16 KB) via load-buffer/paste-buffer, ssh window without a shell, exact session target, missing END marker is an error, remote stdin /dev/null. Decisions: surfaces as options, robot-* into cca doctor, CMD words joined like ssh, output captured on both transports, run.tokf (doc-1 cca run, doc-2 [run]).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca run + cca.executor (tmux and ssh, --all, --create-file, --list, --read, --session, [run.log], run.tokf), cca doctor run checks; tests/test_cca_run.py (fake ssh, real tmux on a private socket); tests/run-all.sh green (721 pytest); plan and diff reviewed.
<!-- SECTION:FINAL_SUMMARY:END -->
