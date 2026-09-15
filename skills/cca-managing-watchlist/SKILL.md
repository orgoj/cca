---
name: cca-managing-watchlist
description: Manages watchlist.json via cca-watchlist script - returns JSON data for main session processing
allowed-tools: Bash(*)
---

# Watchlist Manager Agent

Query cca-watchlist script and return raw JSON output for main session to process.

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
  during an outage to see both fields. Return to work with `activate`, then reassess
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
| `list --standby` | Standby only, including blocked items; shows trigger and what to capture. Alias of `--state standby`. |
| `list --current` | Notes valid today, idle by default; local inclusive validity bounds. |
| `list --expired` | Notes whose `valid_until` is before today, idle by default. |
| `list` / `search` | Active, idle and standby, including notes; `--all` also includes done. Explicit filters still apply. |

Use optional `valid_from` and `valid_until` (`YYYY-MM-DD`) for notes. Missing bounds
are unlimited: a note without `valid_until` never expires. Note dates use the
machine's local date; work scheduling retains UTC. Show current information with
`list --type note --current`, separately from daily tasks. `--all` or an explicit
`--state done` can include closed notes in validity queries.

**Operations:**
- `cca-watchlist list-today` - All tasks needing check today (active only).
- `cca-watchlist list [--area X] [--state X] [--type X] [--all] [--json]` - Full register,
  grouped by area.
- `cca-watchlist show <id> [--json]` - One item.
- `cca-watchlist search "query" [--json]` - Substring match across every text field, idle included.
- `cca-watchlist update <id>` - Update timestamp.
- `cca-watchlist add-routine|add-task|add-incident|add-note ...` - Create an item;
  tasks and notes default to `idle`, routines and incidents to `active`.
- `cca-watchlist edit <id> --<field> <value>` - Change fields; **never hand-edit the JSON.**
- `cca-watchlist park|standby|activate|done <id>` - Move between states.
- `cca-watchlist remove <id>` - Delete permanently.
- `cca-watchlist migrate` - One-off upgrade of a v1 file (no `state`, `enabled` flag) to v2.

**Time-Based Filtering:**
- Get all items (`cca-watchlist list --all --json`).
- Filter JSON by `last_check` field using calculated cutoff.

### 3. Output
**Return Output:**
- Return raw JSON output with timestamp context.
- **Include current_time** in JSON output.

## Output Format

Return script's JSON output directly with timestamp context:

```json
{
  "current_time": "2025-10-16 14:30",
  "items": [
    {
      "id": "server1-oom",
      "type": "incident",
      "name": "server1 OOM kills",
      "file": "incidents/2025-10-14-oom-kill-server1-services.md",
      "last_check": "2025-10-15T07:20:00",
      "status": "monitoring",
      "risk": "MEDIUM",
      "job_description": "Memory pressure monitoring"
    }
  ]
}
```

## Critical Rules

- **ALWAYS start with `date`** - needed for time calculations
- **Return raw JSON** - main session processes it (no markdown formatting)
- **Script handles filtering** - use appropriate command, don't re-filter in agent
- **For time-based queries** - get all items, then filter by timestamp
- **Include current_time** in JSON output - main session needs context


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
