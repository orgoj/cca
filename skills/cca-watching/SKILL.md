---
name: cca-watching
description: Daily watchlist check - routine monitoring and active incident verification
allowed-tools: TaskCreate(*), TaskUpdate(*), Bash(*), Read(*)
---

# Watch - Daily Watchlist Check

Query watchlist, create task list (TaskCreate), display summary.

## Steps

### 1. Analysis
**Load watchlist commands first:** Load skill `cca-managing-watchlist` before running any
`cca-watchlist` search or update command; it defines the register's states, selection rules and
safe mutations.

**Query watchlist:** For the daily check, use `cca-watchlist list-today` (from PATH). For
`cca-watching QUERY`, use `cca-watchlist search "QUERY" --json`. Run either from the project root —
the command reads `watchlist.json` from the current directory and exits non-zero if there is none.
An error here means a wrong working directory, not an empty result.
**Parse JSON:** Extract today's tasks (routines and active incidents).

⛔ **`list-today` returns only `state=active` items.** The same register also holds `idle` backlog
work, which is deliberately NOT part of the daily check — do not pull it in with `list`/`search`
unless the user asks for it. States and commands: skill `cca-managing-watchlist`.

### 2. Execution
**Process Items:**
- **Load server context**: If checking incidents, identify the affected server and read its guide
  (typically `cca/guides/servers/{name}.md`, find it via `tantivy2agents search "{servername}"`).
  Server docs are guides read with `Read` — `Skill({ skill: "server-{name}" })` does not exist.
- **Execute Routines**: If the description names a skill or command, run it.

### 3. Tasks & summary
**Create tasks**: Each item as separate task (TaskCreate; TaskUpdate in_progress/completed during checks).
**Display summary**: Task names and last check times.
**Update timestamps**: After loading skill `cca-managing-watchlist`, use
`cca-watchlist update <id>` for each completed check.

## Usage

- `cca-watching` - All tasks needing check today
- `cca-watching routine only` - Only routine tasks today
- `cca-watching QUERY` - Search specific items

## How to Handle Checks

- **Load server context first**: When checking an incident, identify the affected server from the
  incident name and read its server guide BEFORE reading the incident file
- **Routines with commands**: If `description` names a skill or command → run it
- **Mark completed**: TaskUpdate status after each check

## Output Format

```
Watchlist prepared: X items
- Task name 1 (last check: 2025-10-16 09:00)
- Task name 2 (last check: never)
- Task name 3 (last check: 2025-10-15 14:30)

Ready to proceed.
```

---

*Daily morning routine to verify all systems stable and no incidents worsening.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
