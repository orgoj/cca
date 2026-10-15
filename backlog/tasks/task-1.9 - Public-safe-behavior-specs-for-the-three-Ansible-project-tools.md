---
id: TASK-1.9
title: Public-safe behavior specs for the three Ansible-project tools
status: To Do
assignee: []
created_date: '2026-10-15 07:36'
labels: []
dependencies: []
parent_task_id: TASK-1
priority: high
type: docs
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
check-open-ports, netdata-cli.py and cloudflare-cli live in a private consumer project, so ports and the config schema could not be done from a clone. Their observable behavior is captured once in public-safe specs that the port tasks and doc-2 use instead of the sources.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog/docs holds one spec per tool: commands, flags, defaults, inputs/config files, output paths, exit codes, external tools, network calls
- [ ] #2 Specs contain no consumer-specific names, hosts, zones or paths; test-shared-clean passes with the consumer denylist
- [ ] #3 Each spec lists intentional changes for the cca port (config from .cca.toml, secrets from sops, English texts)
<!-- AC:END -->
