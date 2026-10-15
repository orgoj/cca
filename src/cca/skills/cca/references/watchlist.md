# cca watchlist

The daily check over the project's Backlog.md: recurring checks, scheduled tasks and
dated notes. Everything else is plain `backlog` (create, edit, search, refs, priority,
dependencies, Done).

```
cca watchlist today [--json]
cca watchlist notes [--on YYYY-MM-DD] [--search TEXT] [--json]
cca watchlist checked ID [--json]
```

Conventions (labels and the project status `Note`):

| What | How |
|---|---|
| recurring check | open task with label `every:Nd` (N days, 1-366); its due date is the next check; optional `until:YYYY-MM-DD` ends the checking |
| scheduled task | any open task with a due date |
| note | information, never work: status `Note`, optional `from:YYYY-MM-DD` / `until:YYYY-MM-DD` (inclusive local dates, missing = unlimited) |

Create them with backlog, for example:

```
backlog task create "Status check" -l every:1d --due-date 2026-10-15 --ref cca/guides/status.md
backlog task create "Power maintenance" -s Note -l from:2026-09-16,until:2026-09-17 -d "Possible outage"
```

`today`: open tasks due today or earlier (`ID | due | +Nd overdue | every:Nd or - | title`,
oldest first, then priority; `[ended]` = past its `until:`, run `checked` to close it),
then the notes valid today (`ID | from..until | title`, `*` = open). Do the checks, then
`checked ID` for each recurring one; finish a one-off scheduled task with
`backlog task edit ID -s Done`.

`notes --on DATE`: notes valid on a date, e.g. what was planned when an outage
happened; `--search` narrows by text.

`checked ID`: sets the due date to today + N days and adds a `checked` comment; when that
would pass `until:`, sets the task Done instead. Refuses tasks without one valid
`every:` label and tasks in status Note or Done.

`backlog` runs in the `.cca.toml` directory. Exit 0 OK; 1 a task has a malformed
`every:`/`from:`/`until:` label (named on stderr, the rest is still listed); 2 usage,
configuration or backlog error. `cca doctor` checks that `backlog` is installed and
the statuses include `Note` and `Done`.
