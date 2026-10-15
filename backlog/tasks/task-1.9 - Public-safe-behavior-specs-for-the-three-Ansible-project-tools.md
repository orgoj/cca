---
id: TASK-1.9
title: Public-safe behavior specs for the three Ansible-project tools
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:36'
updated_date: '2026-10-15 09:30'
labels: []
dependencies: []
references:
  - private consumer project; maintainer with access delivers the specs
parent_task_id: TASK-1
priority: high
type: docs
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
check-open-ports, netdata-cli.py and cloudflare-cli live in a private consumer project, so ports and the config schema could not be done from a clone. Their observable behavior is captured once in public-safe specs that the port tasks and doc-2 use instead of the sources. Done only by the CCA maintainer with access to that project; the committed specs are the deliverable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog/docs holds one spec per tool: commands, flags, defaults, inputs/config files, output paths, exit codes, external tools, network calls
- [x] #2 Specs contain no consumer-specific names, hosts, zones or paths; test-shared-clean passes with the consumer denylist
- [x] #3 Each spec lists intentional changes for the cca port (config from .cca.toml, secrets from sops, English texts)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added public-safe legacy behavior specs doc-3 (open-ports), doc-4 (netdata), doc-5 (cloudflare) with commands, flags, defaults, files, exit codes, tools, network calls and intentional changes; doc-2 placeholder reserves the schema ID for TASK-1.6; spec refs on TASK-1.2.1/1.2.2/1.2.3/1.6. Reviewed against the sources (all findings fixed); shared-clean check with the consumer denylist passed.
<!-- SECTION:FINAL_SUMMARY:END -->
