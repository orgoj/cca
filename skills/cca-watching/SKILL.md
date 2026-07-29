---
name: cca-watching
description: Daily watchlist check - routine monitoring and active incident verification
allowed-tools: TaskCreate(*), TaskUpdate(*), Bash(*), Read(*)
---

# Watch - Daily Watchlist Check

Query watchlist, create task list (TaskCreate), display summary.

## Steps

### 1. Analysis
**Query watchlist:** Use `cca-watchlist` script (from PATH).
**Parse JSON:** Extract today's tasks (routines and active incidents).

### 2. Execution
**Process Items:**
- **Load server context**: If checking incidents, identify affected server -> read the project's `server-{servername}/SKILL.md` doc (find via `tantivy2agents search "{servername}"`).
- **Execute Routines**: If description contains slash command, execute it.

### 3. Tasks & summary
**Create tasks**: Each item as separate task (TaskCreate; TaskUpdate in_progress/completed during checks).
**Display summary**: Task names and last check times.
**Update timestamps**: Use `cca-watchlist update` after checks complete.

## Usage

- `/cca:watching` - All tasks needing check today
- `/cca:watching routine only` - Only routine tasks today
- `/cca:watching QUERY` - Search specific items

## How to Handle Checks

- **Load server context first**: When checking incidents, identify affected server from incident name → read the project's `server-{servername}/SKILL.md` doc BEFORE reading incident file
- **Routines with commands**: If `description` contains "Use slash command /cca:..." → Execute that command
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
