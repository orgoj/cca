# cca checkouts

Compares local checkouts of one repository, e.g. a library repository embedded in
several projects that is synced between them by hand.

```
cca checkouts PATH PATH [PATH...]
```

- Read-only: no fetch, merge, push or index refresh; repository fsmonitor hooks are
  never run. Paths are relative to the current directory.
- Per checkout `[N] PATH`, then its branch (`(detached)`), HEAD and `clean` or
  `K uncommitted` with the `git status --porcelain` lines.
- `--- missing commits ---`: per checkout `[N] lacks K` and the commits reachable from
  another checkout's HEAD but not from its own, `hash subject (in [M]...)`. Lists stop
  after 30 entries (`... K more`). Commits match by hash: a cherry-picked or rebased copy
  shows as missing on both sides. `WARN no common commit` when the histories are unrelated.
- Last line and exit status: `IN SYNC: identical HEAD ..., all clean` (0) or
  `DIVERGED: N different HEADs, uncommitted changes in [N]` (1). A path that is not a git
  work tree, a path given twice, fewer than two paths or no `git` → exit 2.
- Use it to plan a sync (which side needs which commits) and to verify it afterwards
  (exit 0). It compares local state only: fetch or pull in each checkout first when
  remote commits matter.
