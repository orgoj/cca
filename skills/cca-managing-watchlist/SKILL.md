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

**Operations:**
- `cca-watchlist list-today` - All tasks needing check today.
- `cca-watchlist search "query"` - Search specific items.
- `cca-watchlist update <id>` - Update timestamp.
- `cca-watchlist disable/enable/remove <id>` - Manage items.

**Time-Based Filtering:**
- Get all items (`cca-watchlist search ""`).
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
