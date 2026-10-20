---
id: TASK-9
title: Packaged cca skill replaces every old cca-* skill
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-20 14:39'
updated_date: '2026-10-20 14:43'
labels: []
dependencies: []
priority: high
type: docs
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
User decision: the packaged skill cca alone must suffice; all old cca-* skills are removed from projects. Fold the generic knowledge workflow (writing rules, tantivy2agents search, incidents, guides, lessons, monthly maintenance), problem solving, server discovery, log analysis, safety/secret rules, hetrix outage investigation and the daily check into references of the packaged skill.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 references knowledge, records, maintenance, operations added; hetrix and watchlist extended; SKILL.md workflow table; every root skill mapped in doc-6 Skills
- [x] #2 maintenance changes only after a report and user approval; diagnostics never print secrets
- [x] #3 plan, security and result review done; tests/run-all.sh and shared-clean with the consumer denylist green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Packaged skill cca replaces every old cca-* skill: references knowledge, records, maintenance, operations; hetrix Outage investigation; watchlist Daily check and Setup; SKILL.md workflow table; doc-6 Skills mapping of all 19 root skills. Plan, security (agent_security) and result (agent_review) reviews approved.
<!-- SECTION:FINAL_SUMMARY:END -->
