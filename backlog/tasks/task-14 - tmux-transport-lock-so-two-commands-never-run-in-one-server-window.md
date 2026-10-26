---
id: TASK-14
title: 'tmux transport: lock so two commands never run in one server window'
status: Done
assignee:
  - '@cca_dev'
created_date: '2026-10-26 08:42'
updated_date: '2026-10-26 08:47'
labels:
  - executor
  - tmux
dependencies: []
priority: medium
type: bug
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The tmux transport has no lock: a second cca run on the same server pastes its line into the pane while the first command still runs (or after it timed out). The text queues as terminal typeahead; a first command reading the terminal (sudo password prompt, less, y/N question) consumes the second command as its input. Two concurrent first calls on a server without a window can also open two windows with the same name. Fix: before pasting, check the pane: a last START marker without END means busy -> refuse with the marker and the cca run --read --marker hint (covers timed-out commands too); hold a short local flock (per tmux session + server, e.g. in the user runtime dir) around check + window creation + paste so concurrent calls cannot both pass. tmux backend is POSIX-only, flock is fine there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 cca run over tmux refuses (distinct error, names the running marker and the --read hint) when the server's pane has a START marker without END, also after an earlier timeout
- [x] #2 Concurrent cca run calls on one server never both paste: the second waits briefly or is refused while the first holds the lock
- [x] #3 Concurrent first calls on a server without a window create exactly one window
- [x] #4 Tests with the real tmux test server cover busy pane, timed-out leftover and concurrency; docs in references/run.md and --help
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
tmux transport: running_marker() refuses a call while the pane's last START marker has no END (exit 2, names the marker and the --read --marker hint; covers timed-out commands). WindowLock: per-user flock (tmux session + server, 0700 dir cca-UID under the temp dir) held from the busy check through window creation and paste until the own START marker shows; a second caller waits up to LOCK_WAIT=10s, then is refused. cca run --session takes the same lock. Tests on the real tmux server: busy pane, timed-out leftover, concurrent first calls (one window, one refused; fails without the lock), lock wait. Docs: references/run.md, --help epilog, doc-1. tests/run-all.sh ALL PASSED, 877 pytest.
<!-- SECTION:FINAL_SUMMARY:END -->
