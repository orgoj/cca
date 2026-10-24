---
id: TASK-12
title: 'executor: cap captured remote output'
status: To Do
assignee: []
created_date: '2026-10-24 07:35'
labels:
  - executor
  - security
dependencies: []
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Review of cca ioc (agent_review): executor.execute reads ssh/tmux output with no byte limit, so a compromised host can exhaust local memory before the timeout. cca ioc bounds its state reads remotely (head -c), but a hostile remote shell can still send any stream. Add a hard cap in _ssh_execute (streamed read, kill on overflow, distinct exit) and document it for cca run/server/ioc.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ssh transport output over the cap stops the call with a clear error
- [ ] #2 test with a fake ssh printing more than the cap
<!-- AC:END -->
