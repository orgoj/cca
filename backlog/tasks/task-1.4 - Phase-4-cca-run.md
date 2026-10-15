---
id: TASK-1.4
title: 'Phase 4: cca run'
status: To Do
assignee: []
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 07:17'
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
Python successor of cca-tmux-cli built from tmux_cli_python/, replacing cca-run-on-server and cca-run-all. The command shape is a public contract for external validators (Dippy).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 cca run SERVER -- CMD and cca run SERVER with quoted heredoc stdin work over tmux and ssh transports chosen in .cca.toml
- [ ] #2 Both or neither of -- and stdin script is rejected with a non-zero exit
- [ ] #3 cca run --all covers cca-run-all behavior
- [ ] #4 Compatibility matrix vs cca-tmux-cli (robot-init, doctor, robot-help, exit codes, Ctrl-C/SIGTERM markers, logging, tokf) with every row tested
- [ ] #5 tmux_cli_python/ package, its YAML config and pyyaml/typer/libtmux deps are removed or folded into cca.commands.run; its settings live in .cca.toml
- [ ] #6 The final cca run option list is published in doc-1 and sent to the Dippy maintainer before release
<!-- AC:END -->
