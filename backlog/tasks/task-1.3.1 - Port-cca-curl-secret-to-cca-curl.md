---
id: TASK-1.3.1
title: Port cca-curl-secret to cca curl
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:32'
updated_date: '2026-10-15 15:45'
labels: []
dependencies:
  - TASK-1.1
parent_task_id: TASK-1.3
priority: medium
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cca-curl-secret puts {TOKEN} URL substitutions in curl argv (visible in the process list), does not redact secrets that curl itself prints (-v, --trace, -w, error messages) and picks credentials by a hostname-derived id. cca curl is a light wrapper that hides authorization from the agent: every curl option passes through; which calls are allowed is the job of the command validator, not of cca curl.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every curl option passes through unchanged (option table read from the installed curl, short clusters and -- handled), except -L/--location/--location-trusted, -K/--config and --expand-url, also as --expand- forms (exit 2); each rejection a negative test
- [x] #2 Exactly one HTTPS URL (positional or --url), validated by doc-2 HTTPS URLs; credential selected by origin or --cred-id within the origin; a second URL rejected; ambient .curlrc disabled (-q)
- [x] #3 Configured secrets never in curl argv or CCA diagnostics: credentials, the URL and every option value with {TOKEN} reach curl through a config on stdin; values escaped, control characters rejected
- [x] #4 Secrets (bearer, password, base64 user:password, URL-encoded forms) redacted from curl stdout and stderr and from files curl writes request data to (--trace, --trace-ascii, --libcurl, --stderr, -D, -w %output{}); -o output passes unchanged; tests incl. {TOKEN} URLs and a reflected-token fixture
- [x] #5 Reference for cca curl in the shipped cca skill, SKILL.md and README rows; root skills/ untouched; tests/run-all.sh green (released with the complete cca, TASK-1.11)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added cca curl (src/cca/commands/curl.py): every curl option passes through, parsed with the option table of the installed curl (--help all); -L/--location-trusted/-K/--expand-url (and --expand- forms) rejected; one HTTPS URL, credential by origin or --cred-id; credentials, URL and {TOKEN} values go to curl as a config on stdin; secrets (incl. base64, URL-encoded and escaped forms) redacted from stdout/stderr and request-data files; -o unchanged; SSLKEYLOGFILE dropped. cli RAW_ARGS hook passes wrapper args unparsed. Per user decision no legacy compatibility matrices: doc-1 and AC of 1.3.x/1.4 rewritten. Verified with tests/test_cca_curl.py (57 tests, one with real curl) and tests/run-all.sh ALL PASSED; code and security reviews passed (thread cca-task-1-3-1).
<!-- SECTION:FINAL_SUMMARY:END -->
