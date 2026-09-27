---
name: cca-managing-watchlist
description: Manage watchlist.json with cca-watchlist; use agenda for what to do, ready for a given time and window, ranked search for discovery, and brief edit confirmations.
allowed-tools: Bash(*)
---

# Watchlist Manager Agent

Use `cca-watchlist` to find, inspect, and update watchlist items. Keep discovery output short.

## Steps

### 1. Analysis
Run `date +%Y-%m-%d\ %H:%M` only when the current date and time are not already in context.
Use it for time-based filtering and relative time calculations.

### 2. Execution
**Run it from the project root.** The script resolves `watchlist.json` from the current directory
(`$CCA_WATCHLIST` → `./cca/watchlist.json` → `./watchlist.json`) and exits non-zero when it finds
none. If that error appears, fix the working directory — never treat an empty list as "nothing to
check today".

**Types:** `routine` (recurring check), `incident` (incident follow-up), `task`
(work item), `note` (information with optional validity dates, never work).

**States (schema v2)** — every item is `active`, `idle`, `standby` or `done`:
- `active` — takes part in the daily check, i.e. `list-today`.
- `idle` — backlog: **never** in `list-today`, but found by `search` and `list`. Requires at
  least one `--refs` entry for work items, because full context belongs in an incident or guide.
  A bare filename (`2026-01-15-thing.md`) is looked up in `incidents/`, `incidents/archive/*/`,
  `deniky/` and `guides/`; an entry containing `/` is resolved relative to the project root.
- `done` — finished; hidden unless `--all`.
- `standby` — deliberately wait until the event in `description` happens; set
  `next_action` to **what evidence to capture** at that moment. Use `list --standby`
  to find an item and `show ID` to see both fields. Return to work with `activate`, then reassess
  `prio`. Notes can only be `idle` or `done`.

Keep `blocked_on` independent of state: standby means **we do not want to work
until the event occurs**; blocked means **we want to work but cannot**. Do not put
the standby trigger in `blocked_on`. A standby item may also have a real blocker;
`standby` and `activate` preserve it. Clear a resolved blocker explicitly with
`edit ID --blocked-on ''`.

**Priority:** use `prio` exclusively to order work, never to encode incident
severity (`risk`). A severe incident whose work is deferred is `p3`. Do not assign
`p1` to standby items or items with nonempty `blocked_on`. These are authoring
rules; the CLI does not rewrite or reject priorities based on state/blockers.

**Selections:**

| Command | States and selection |
|---------|----------------------|
| `agenda` | Start here for "what should we do?": due active checks ordered by UTC deadline, then actionable p1 work fitting default 1h/wany. One 20-row text summary; use `show ID` for details. |
| `list-today` | Active work due for a check; excludes notes, idle, standby and done. |
| `ready` | Use when time or window is specified. Active/idle work fitting time and effective window; excludes blockers unless `--include-blocked`. Missing effort goes in `untagged`. Standby/notes/done never enter either result. Text is compact; `--verbose` adds actions, `--json` returns all items. |
| `next` | One active/idle, unblocked, tagged action fitting constraints, with nonempty `next_action` and no future `check_after`; ordered by priority, effort, ID. Defaults: 1h and wany. Returns an object or null without writing. |
| `list --standby` | Standby only, including blocked items; use `show ID` for trigger and capture details. Alias of `--state standby`. |
| `list --current` | Notes valid today, idle by default; local inclusive validity bounds. |
| `list --expired` | Notes whose `valid_until` is before today, idle by default. |
| `list` / `search` | Active, idle and standby, including notes; `--all` also includes done. Explicit filters still apply. |

Use optional `valid_from` and `valid_until` (`YYYY-MM-DD`) for notes. Missing bounds
are unlimited: a note without `valid_until` never expires. Note dates use the
machine's local date; work scheduling retains UTC. Show current information with
`list --type note --current`, separately from daily tasks. `--all` or an explicit
`--state done` can include closed notes in validity queries.

**Discovery:** Start with the most specific known ID, name or keywords. `search`
requires every query word to match somewhere in the item; ID/name/keywords matches
rank above description/next-action matches. Reference-only matches require `--deep`.
By default, search checks active, idle and standby; `--all` adds done and `--state X`
selects one state. One match displays full detail. Use `search "term" --brief` to
check for a duplicate before adding, and `show ID` for later detail. Multiple
matches show short ID/name lines; if more than 20 match, refine the query.
`list` keeps state, type, area and priority on one line per item; `list-today` shows
priority, effort and due age. Both cap text at 20 items.
Avoid `--json` on discovery commands unless the caller needs full machine-readable data.

**Operations:**
- `cca-watchlist agenda` - Short default work agenda; use for "what should we do?".
- `cca-watchlist list-today [--type X]` - Active items due today.
- `cca-watchlist list [--area X] [--state X] [--type X] [--all]` - Compact register.
- `cca-watchlist show <id> [--json]` - Complete details for one item.
- `cca-watchlist search "specific words" [--deep] [--all] [--state X] [--brief]` - Ranked word search.
- `cca-watchlist update <id>` - Update timestamp.
- `cca-watchlist add-routine|add-task|add-incident|add-note ...` - Create an item;
  tasks and notes default to `idle`, routines and incidents to `active`.
- `cca-watchlist edit <id> --<field> <value>` - Change fields; **never hand-edit the JSON.**
- Common `edit` and `add-*` flags: `--name`, `--description`, `--check-after`,
  `--next-action`, `--status`, `--prio`, `--effort`, `--change-risk`, `--window`,
  `--refs`, `--blocked-on`. `add-incident` also requires `--file` and `--status`.
- `cca-watchlist rename <old-id> <new-id>` - Change only the canonical slug ID; preserve item fields and order.
- `cca-watchlist park|standby|activate|done <id>` - Move between states.
- `cca-watchlist remove <id>` - Delete permanently.
- `cca-watchlist migrate` - One-off upgrade of a v1 file (no `state`, `enabled` flag) to v2.

`edit --next-action` and `edit --status` record `last_check` automatically. If the
remaining `check_after` is past, read the warning and decide whether to reschedule it.
Changing a name does not change its ID; use `rename` when the ID should change too.

Item mutations (`add-*`, `edit`, `rename`, `update`, `park`, `standby`, `activate`, `done`)
print a one-line `<command>: <ID>` confirmation. Add `--json` only when the
full updated item is needed; `show ID --json` can retrieve it later.

**Time-Based Filtering:** If a query needs a custom `last_check` cutoff that the CLI
cannot select, get all items with `cca-watchlist list --all --json` and filter by timestamp.

### 3. Output

Return only the relevant IDs and requested facts. For one item, use `show ID --json`
when the caller needs structured fields. Include the current time when interpreting
relative dates or time cutoffs.

## Critical Rules

- Run `date` only when the current date and time are not already in context.
- **Use the CLI's selectors** before inspecting an item; only custom time cutoffs need local filtering.
- **Use `show` for details** instead of expanding a whole discovery result.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
