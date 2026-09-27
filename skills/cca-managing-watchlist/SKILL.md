---
name: cca-managing-watchlist
description: Manage and query watchlist.json with cca-watchlist; find precise matches with compact search and inspect one item with show.
allowed-tools: Bash(*)
---

# Watchlist Manager Agent

Use `cca-watchlist` to find, inspect, and update watchlist items. Keep discovery output short.

## Steps

### 1. Analysis
**Mandatory First Step:** Run `date +%Y-%m-%d\ %H:%M`
- Needed for time-based filtering and relative time calculations.

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
| `list-today` | Active work due for a check; excludes notes, idle, standby and done. |
| `ready` | Active/idle work fitting time and effective window; excludes blockers unless `--include-blocked`. Missing effort goes in `untagged`. Standby/notes/done never enter either result. |
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

**Discovery:** Start with the most specific known ID, name, area term, or reference fragment.
`search` matches every text field, so broad project or host terms can match most items.
Use the compact text output of `search`, `list`, or `list-today` to identify IDs, then
`show ID` for the needed detail. These listings show at most 20 items; if truncated,
refine the search term or list filters. Avoid `--json` on discovery commands unless
the caller needs the full machine-readable register.

**Operations:**
- `cca-watchlist list-today [--type X]` - Active items due today.
- `cca-watchlist list [--area X] [--state X] [--type X] [--all]` - Compact register.
- `cca-watchlist show <id> [--json]` - Complete details for one item.
- `cca-watchlist search "specific query"` - Substring match across text fields, idle included.
- `cca-watchlist update <id>` - Update timestamp.
- `cca-watchlist add-routine|add-task|add-incident|add-note ...` - Create an item;
  tasks and notes default to `idle`, routines and incidents to `active`.
- `cca-watchlist edit <id> --<field> <value>` - Change fields; **never hand-edit the JSON.**
- `cca-watchlist park|standby|activate|done <id>` - Move between states.
- `cca-watchlist remove <id>` - Delete permanently.
- `cca-watchlist migrate` - One-off upgrade of a v1 file (no `state`, `enabled` flag) to v2.

**Time-Based Filtering:** If a query needs a custom `last_check` cutoff that the CLI
cannot select, get all items with `cca-watchlist list --all --json` and filter by timestamp.

### 3. Output

Return only the relevant IDs and requested facts. For one item, use `show ID --json`
when the caller needs structured fields. Include the current time when interpreting
relative dates or time cutoffs.

## Critical Rules

- **ALWAYS start with `date`** - needed for time calculations
- **Use the CLI's selectors** before inspecting an item; only custom time cutoffs need local filtering.
- **Use `show` for details** instead of expanding a whole discovery result.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
