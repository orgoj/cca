---
id: TASK-1.2.2
title: Port netdata
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 13:41'
labels: []
dependencies:
  - TASK-1.1
  - TASK-1.9
references:
  - doc-4
parent_task_id: TASK-1.2
priority: high
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Port of netdata-cli.py (stdlib; Netdata API directly or over ssh; fping cache) from the public-safe spec written in TASK-1.9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Server addresses come from [servers] in .cca.toml; cache paths from doc-2 keys
- [x] #2 Compatibility matrix derived from the TASK-1.9 spec; every row tested, incl. ssh vs direct transport and fping paths
- [x] #3 tests/run-all.sh green incl. fixture denylist (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added cca netdata (list, query, stats, top, fping incl. --per-target/--history/--all, discover, meta) from doc-4: servers from [servers] in .cca.toml, ssh transport via cca.ssh or direct HTTP without env proxies, fping cache names and dir per doc-2, per-server transport in fping --all, correlated verdict only for >= 2 servers (single server: own path or asymmetric fault), usage errors exit 2, fetch errors exit 1. API strings escaped for the terminal, 64 MiB response cap and total deadline. Compatibility matrix in doc-4, every row tested in tests/test_cca_netdata.py; skill reference, SKILL.md and README rows.
<!-- SECTION:FINAL_SUMMARY:END -->
