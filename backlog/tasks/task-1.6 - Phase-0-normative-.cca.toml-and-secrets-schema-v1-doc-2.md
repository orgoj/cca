---
id: TASK-1.6
title: 'Phase 0: normative .cca.toml and secrets schema v1 (doc-2)'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 12:25'
labels: []
dependencies:
  - TASK-1.9
references:
  - doc-3
  - doc-4
  - doc-5
parent_task_id: TASK-1
priority: high
type: docs
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The core config API is public contract; later ports must not change it silently. Old tools read many CCA_* variables and ad-hoc files (doc-1 Config lists them) whose new place must be fixed before implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog/docs doc-2 defines every table, key, type, default and validation rule of schema v1
- [x] #2 doc-2 maps every legacy input listed in doc-1 Config to a .cca.toml key or marks it intentionally dropped
- [x] #3 doc-2 defines the sops file shape for each secret-using command, incl. curl allowed origins and cloudflare api_token
- [x] #4 Valid and invalid TOML fixtures for schema v1 exist under tests/fixtures/ for the core tests
- [x] #5 doc-2 carries the cca curl request-policy fields (allowed origins with scheme, host, port) from doc-1
- [x] #6 doc-2 defined the [legacy] table and exclusion list for cca doctor --legacy (removed in TASK-1.8: no project content scan, manual conversion in TASK-4)
- [x] #7 doc-2 lists the agent skill install dirs checked by cca doctor for old CCA links (doc-2 Old CCA links)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
doc-2 now defines .cca.toml schema v1 (general/URL/file-name rules, every table and key with type, default, validation; load vs use time), maps every legacy input from doc-1 and the bash sources, defines the curl (origins, auth, selection by origin) and cloudflare sops shapes, and the agent skill dirs checked for old CCA links. User decisions: ssh defaults to server name, explicit [run.log], mongodb status runs on the server, configurable [secrets] paths. Fixtures: tests/fixtures/cca-toml/{valid,invalid} and tests/fixtures/sops-shapes (all parsed; only syntax-error.toml fails TOML by design). Code and security reviews closed with no findings. The [legacy] table, exclusions and containment rules defined here were removed in TASK-1.8 by user decision (no doctor --legacy; one-time manual conversion in TASK-4).
<!-- SECTION:FINAL_SUMMARY:END -->
