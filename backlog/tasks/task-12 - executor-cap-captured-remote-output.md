---
id: TASK-12
title: 'executor: cap captured remote output'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-24 07:35'
updated_date: '2026-10-26 08:08'
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
- [x] #1 ssh transport output over the cap stops the call with a clear error
- [x] #2 test with a fake ssh printing more than the cap
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
_ssh_execute reads output in 64 KiB chunks in a thread; past OUTPUT_MAX (16 MiB) ssh's process group is killed, the output discarded and execute raises CcaError exit 125 (logged as output-limit). cca run --all and cca server stop; cca ioc reports it as a host error and goes on. tmux transport is bounded by tmux history-limit, unchanged. Docs: references run/server/ioc and --help of run/server.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Hard 16 MiB cap on ssh output (exit 125, ssh killed); tests with fake ssh: endless output stopped fast, boundary 1000/1001 bytes, --all stops and logs output-limit. run-all ALL PASSED (870 pytest).
<!-- SECTION:FINAL_SUMMARY:END -->
