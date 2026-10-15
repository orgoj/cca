---
id: TASK-1.4
title: 'Phase 4: cca run'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:33'
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
Python successor of cca-tmux-cli, cca-run-on-server and cca-run-all, built from tmux_cli_python/. The command shape is a public contract for external validators (Dippy); see doc-1 cca run. tmux_cli_python has known hazards: hook confirmation runs a stderr-derived message through a shell, server name is interpolated into an ssh shell string, empty redactor output restores the unredacted text, timeout output is printed before redaction.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Compatibility matrices vs cca-tmux-cli (robot-init, doctor, robot-help, list, read, session, exit codes, Ctrl-C/SIGTERM markers, logging, tokf), cca-run-on-server (--list, --create-file) and cca-run-all; every row tested
- [ ] #2 cca run SERVER -- CMD and cca run SERVER with CMD on stdin work over tmux and ssh; no CMD with TTY stdin or empty stdin exits non-zero
- [ ] #3 Surfaces meaningless for a transport (e.g. read over ssh) exit non-zero with a clear error
- [ ] #4 cca run --all runs a named local CCA script once per server and stops on the first failure
- [ ] #5 Hook confirmations run as argv with the message as one argument or stdin; tests with malicious messages and server names show no local shell execution on both transports
- [ ] #6 SERVER only from [servers]; ssh target validated and passed as separate argv
- [ ] #7 Redaction covers normal, timeout, error and log output; empty redactor output stays empty; regression tests
- [ ] #8 tmux_cli_python package, its YAML config and unneeded deps are removed; its settings live in .cca.toml per doc-2
- [ ] #9 Skills referencing cca-tmux-cli or cca-run-on-server updated in the same release; released as its own tag
<!-- AC:END -->
