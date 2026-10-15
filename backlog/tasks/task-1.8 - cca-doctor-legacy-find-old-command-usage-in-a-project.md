---
id: TASK-1.8
title: 'cca doctor --legacy: find old command usage in a project'
status: To Do
assignee: []
created_date: '2026-10-15 07:35'
updated_date: '2026-10-15 07:43'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1
priority: medium
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Old cca-* commands are removed once consumers migrate. On each deployment the consumer projects must be checked for remaining references (scripts, Makefiles, CI, docs, skills, agent instructions), otherwise removal breaks them silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reports every reference to a retired command and every legacy config input (.cca-env, .env CCA_* keys, .cca-tmux-cli, .tmux-cli-python.yaml, .netdata-servers, mapped CCA_* variables) with file and line; exits non-zero when any is found
- [ ] #2 Lines or files marked with a cca-legacy-ok annotation, or paths in [legacy] allow, are reported as allowed and do not fail the check (for migration notes)
- [ ] #3 The list of retired commands and inputs ships with cca and grows with each port release
- [ ] #4 README deployment steps require running it in every consumer project after installing a release
- [ ] #5 Always probes the known legacy paths (.cca-env, .env, .cca-tmux-cli, .tmux-cli-python.yaml, .netdata-servers, default agent-instruction files) in the project root and nested repos regardless of git tracking; additionally scans git-tracked files plus [legacy] include, skipping binaries, symlinks and the doc-2 exclusion list; fixtures include ignored/untracked legacy files
<!-- AC:END -->
