---
id: TASK-1.8
title: 'cca doctor --legacy: find old command usage in a project'
status: To Do
assignee: []
created_date: '2026-10-15 07:35'
updated_date: '2026-10-15 07:37'
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
- [ ] #1 Scans git-tracked files of the CWD project (plus paths listed in .cca.toml [legacy] include), skipping binaries, symlinks, vendor/generated dirs listed in doc-2
- [ ] #2 Reports every reference to a retired command and every legacy config input (.cca-env, .env CCA_* keys, .cca-tmux-cli, .tmux-cli-python.yaml, .netdata-servers, mapped CCA_* variables) with file and line; exits non-zero when any is found
- [ ] #3 Lines or files marked with a cca-legacy-ok annotation, or paths in [legacy] allow, are reported as allowed and do not fail the check (for migration notes)
- [ ] #4 The list of retired commands and inputs ships with cca and grows with each port release
- [ ] #5 README deployment steps require running it in every consumer project after installing a release
<!-- AC:END -->
