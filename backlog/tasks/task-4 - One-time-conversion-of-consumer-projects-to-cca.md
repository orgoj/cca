---
id: TASK-4
title: One-time conversion of consumer projects to cca
status: To Do
assignee: []
created_date: '2026-10-15 12:21'
updated_date: '2026-10-15 20:17'
labels:
  - 'blocked:external'
dependencies:
  - TASK-1
priority: low
type: chore
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Starts only after the complete cca CLI is finished, reviewed and approved by the user. Converts each consumer project once by hand following the migration guide (doc-6): writes .cca.toml from its legacy input mapping, moves secrets into sops files, replaces old skill links with cca install skills, switches scripts, Makefiles, CI, docs, skills and agent instructions to cca subcommands, converts watchlist.json items into Backlog.md tasks (doc-1 "Watchlist on Backlog.md"; the project's Backlog.md gets the status Note), and removes legacy config files (.cca-env, .env CCA_* keys, .cca-tmux-cli, .tmux-cli-python.yaml, .netdata-servers, watchlist.json). Decides for each old workflow skill without a successor (doc-6 "Skills") whether it becomes a project skill, is ported into the package by a new task, or is dropped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each consumer project has a valid .cca.toml and no remaining reference to an old cca-* command or legacy config input
- [ ] #2 cca doctor passes in each consumer project
<!-- AC:END -->
