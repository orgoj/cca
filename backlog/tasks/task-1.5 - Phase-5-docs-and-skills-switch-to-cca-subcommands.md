---
id: TASK-1.5
title: 'Phase 5: global docs and migration guide'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-15 07:13'
updated_date: '2026-10-15 20:19'
labels: []
dependencies:
  - TASK-1.2
  - TASK-1.3
  - TASK-1.11
parent_task_id: TASK-1
priority: low
type: docs
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After all ports are released, global docs must describe the cca CLI and give consumers a migration path. Skills are updated with each port; this task is the global cleanup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 AGENTS.md, CLAUDE.md and README describe the cca CLI, install and release
- [x] #2 No file under bin/, lib/ or root skills/ is modified by this task
- [x] #3 A migration guide maps every legacy input from doc-2 to its .cca.toml key or states it was dropped, and requires cca doctor to report no old skill/bin links before TASK-2
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Migration guide is doc-6 (steps, legacy inputs moved from doc-2, old commands, old skills). User decisions: mapping table lives only in doc-6 (doc-2 points to it); old workflow skills without a successor are decided per project in TASK-4. doc-1: misplaced cca run shape/security bullets moved from cca server to cca run. TASK-2 AC #2 and TASK-4 description point to doc-6.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added doc-6 migration guide, rewrote README (cca first, install, config, release, legacy section) and AGENTS.md (cca architecture, commands, conventions); doc-1/doc-2/TASK-2/TASK-4 point to doc-6. Verified with tests/run-all.sh (ALL PASSED, 749 pytest) and shared-clean with the consumer denylist.
<!-- SECTION:FINAL_SUMMARY:END -->
