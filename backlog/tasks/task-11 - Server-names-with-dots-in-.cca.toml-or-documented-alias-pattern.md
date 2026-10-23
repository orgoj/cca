---
id: TASK-11
title: 'Server names with dots in .cca.toml, or documented alias pattern'
status: Idea
assignee: []
created_date: '2026-10-23 20:58'
labels: []
dependencies: []
priority: low
type: enhancement
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reported by two consumer projects converting to cca 1.4.0: [servers.<name>] uses the doc-2 name rule without dots, so FQDN-style legacy server names had to be renamed or aliased and the cca name differs from the hostname (doc-2 mentions the difference only for the ssh key). Suggested direction: decide whether names may contain dots (doc-2 schema change); risks to check: tmux target syntax uses '.' as pane separator (run.transport tmux window names), generated file names, case-insensitive uniqueness. Alternative: document the rename/alias pattern in doc-6 and the skill. Needs analysis before implementation.
<!-- SECTION:DESCRIPTION:END -->
