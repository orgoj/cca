# cca watchlist

The daily check over the project's Backlog.md: recurring checks, scheduled tasks,
priority work and dated notes, plus work selection by time and window. Everything else
is plain `backlog` (create, edit, search, refs, priority, dependencies, Done, archive).

```
cca watchlist today [--json]
cca watchlist notes [--on YYYY-MM-DD] [--expired] [--search TEXT] [--json]
cca watchlist checked ID [--json]
cca watchlist ready [--time 15m|1h|4h] [--window W] [--max-change-risk R] [--area NAME]
                    [--include-blocked] [--verbose] [--json]
cca watchlist next [--time ...] [--window ...] [--max-change-risk ...] [--area NAME] [--json]
cca watchlist migrate FILE [--apply] [--exclude ID]...
```

Conventions (labels, the project status `Note`, the Implementation Plan):

| What | How |
|---|---|
| recurring check | open task with label `every:Nd` (N days, 1-366); its due date is the next check; optional `until:YYYY-MM-DD` ends the checking |
| scheduled task | any open task with a due date, except `idle`/`standby` ones |
| backlog work | label `idle`: never due in `today`; a due date means "not before" for `next`/Priority |
| waiting for an event | label `standby`, the event in the description, what to capture in the plan; never due, never ready |
| blocked | label `blocked:external` (+ `--ref` to the blocker) or an unfinished `--dep` |
| next action | the Implementation Plan: `backlog task edit ID --plan "..."` |
| work tags | `effort:e15\|e1h\|e4h\|exl`, `change-risk:r0..r3`, `window:wany\|woff\|wnight\|wfreeze`, `area:NAME` |
| note | information, never work: status `Note`, optional `from:YYYY-MM-DD` / `until:YYYY-MM-DD` (inclusive local dates, missing = unlimited) |

A task holds the complete work: what and why in the description, the next step in the
plan, the result in acceptance criteria; link longer evidence with `--ref`. Status
`Idea` is never work. The label `watchlist:<id>` marks tasks converted from a legacy
watchlist item.

Create them with backlog, for example:

```
backlog task create "Status check" -l every:1d --due-date 2026-10-15 --ref guides/status.md
backlog task create "Rotate logs on server1" -l idle,effort:e1h,change-risk:r2,area:server1 --priority high
backlog task edit TASK-7 --plan "Run logrotate -f, check free space"
backlog task create "Power maintenance" -s Note -l from:2026-09-16,until:2026-09-17 -d "Possible outage"
```

`today`: open tasks due today or earlier (`ID | due | +Nd overdue | every:Nd or - | title`,
oldest first, then priority; `[ended]` = past its `until:`, run `checked` to close it),
then **Priority** (high-priority tasks that `next` would offer at 1h/wany and are not
due: `ID | priority | effort | window | title`), then the notes valid today
(`ID | from..until | title`, `*` = open). Do the checks, then `checked ID` for each
recurring one; finish a one-off scheduled task with `backlog task edit ID -s Done`.

Daily check:

1. `cca watchlist today` from the project directory (an error means a wrong directory or
   config, never "nothing to do"). Only Due items are the daily check; Priority is a
   reminder, idle work is not pulled in unless the user asks.
2. One session task per Due item. For each: `backlog task view ID --plain`; load the
   server context (server guide, see [operations](operations.md)); for an incident follow-up
   read the server guide before the referenced incident; run the check the task names
   (command, guide or `cca` subcommand).
3. Record the result: `checked ID` for a recurring check, a comment
   (`backlog task edit ID --comment "..."`) for findings, an incident for a new problem.
4. Summary: each item with its result and next due date; open issues.

`notes --on DATE`: notes valid on a date, e.g. what was planned when an outage
happened; `--expired` the notes whose `until:` is before it; `--search` narrows by text.

`checked ID`: sets the due date to today + N days and adds a `checked` comment; when that
would pass `until:`, sets the task Done instead. Refuses tasks without one valid
`every:` label and tasks in status Note or Done.

`ready`: open work (not `Idea`, not `standby`, not blocked unless `--include-blocked`)
whose `effort:` fits `--time` (`exl` never), whose effective window (the stricter of
`window:` and the change-risk minimum: r0/r1 wany, r2 woff, r3 wnight; neither = never)
fits `--window`, and whose `change-risk:` is at most `--max-change-risk`; ordered by
priority, effort, id, 20 rows; tasks without `effort:` are counted as untagged.
`--verbose` shows each next action; `--json` returns the full tasks. `next`: the first
ready task with a plan and no future due date, or `none`.

`migrate FILE`: one-shot conversion of a legacy `watchlist.json` (schema v2) into
tasks; a dry run unless `--apply`. Every item is validated first (all problems listed,
nothing written). Review each line and warning (unresolved ref, ended monitoring,
unknown key) before `--apply`; `--exclude ID` skips machine-only items. Done items are
skipped. A rerun reports converted items as `exists` and creates only the missing ones.

Setup, once per project: `backlog init "<name>" --defaults --integration-mode none --default-editor ""`
(it must not change `AGENTS.md`/`CLAUDE.md`), then statuses
`["Idea", "To Do", "In Progress", "Note", "Done"]` in `backlog/config.yml`.

`backlog` runs in the `.cca.toml` directory. Exit 0 OK; 1 a task has a malformed
watchlist label (named on stderr, the rest is still listed) or `migrate` warned; 2
usage, configuration or backlog error. `cca doctor` checks that `backlog` is installed
and the statuses include `Note` and `Done`.
