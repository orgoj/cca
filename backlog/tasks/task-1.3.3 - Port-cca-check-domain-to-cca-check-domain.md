---
id: TASK-1.3.3
title: Port cca-check-domain to cca check-domain
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 16:42'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of moving every cca-* script to a cca subcommand.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca check-domain options, output and exit codes specified and tested as new behavior; CCA_* inputs from doc-2 keys
- [x] #2 New cca skills for this command added under src/cca/skills/; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cca check-domain DOMAIN: dnspython A/AAAA/CNAME, RDAP owner of foreign addresses (IANA bootstrap, HTTPS-only redirects, informational), hosting marker over connections to the resolved addresses with same-host redirects only, certificate state reported, redirect chain. Config [check_domain] (doc-2). Exit 0 confirmed, 1 not confirmed, 2 usage/config/resolver error. Tests: tests/test_cca_check_domain.py (local DNS, HTTP and HTTPS servers).
<!-- SECTION:FINAL_SUMMARY:END -->
