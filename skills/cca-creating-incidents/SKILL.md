---
name: cca-creating-incidents
description: Create incident documentation after manual problem resolution
argument-hint: "[server] [service] [brief-description]"
allowed-tools: Write(*), Bash(*), Read(*)
---

# Incident-Create - Manual Incident Documentation

Create structured incident documentation after manually resolving a problem.

**Quick create arguments:** $ARGUMENTS

## Steps

### 1. Analysis
**NEJDŘÍV OVĚŘ, ZE INCIDENT UZ NEEXISTUJE:**
- `tantivy2agents search "klicova slova tematu"` (2-4 slova) — pokud tema jiz ma incident (i castecny/
  rozpracovany, napr. TODO polozka s vlastni sekci), **NEZAKLADAT NOVY** — otevri a doplň existujici
  soubor (novou sekci/dodatek s datem), NEnahrazuj puvodni zaznam.
- Pouze kdyz opravdu nic relevantniho neexistuje, pokracuj zalozenim noveho souboru.

**NEJDŘÍV OVĚŘ ČASOVOU OSU:**
- Spusť `date` pro aktuální čas
- Zeptej se uživatele na klíčové timestampy (kdy nahlášeno, kdy vyřešeno)
- **NIKDY nevymýšlej/neodhaduj časy** — fabricated timestamps = user bude naštvaný (incident Feb 12)
- **Kdyz user behem konverzace odkazuje na prave provedenou/aktualni akci** ("ted", "prave ted",
  "prave jsem") — spust `date` OKAMZITE v tu chvili, ne az na konci. Neodvozuj cas z drivejsich
  timestampu v konverzaci.

**Collect incident details** - Interactive questions or use provided arguments.
- Server(s) affected?
- Service(s)?
- Severity? (critical/high/medium/low)
- Brief description?
- Status? (resolved/monitoring/investigating)

### 2. Execution
**Create file** - in the project's CCA incidents directory: `<cca-root>/incidents/YYYY-MM-DD-brief-description.md`. When CCA lives in a subdir, this is `cca/incidents/`. Verify where existing incidents live and write there — never invent a new top-level `incidents/`.
**Pre-fill template** - YAML frontmatter + sections ready to fill.

### 3. Verification
**Auto-indexed** - Search index updates automatically, no manual action needed.
**Confirm file creation** - Output the path to the created file.

**Mitigation status** - A mitigation applied after the incident traffic ended is `monitoring`, not
verified `resolved`. Record the deployment timestamp and the exact condition for future verification.

## Usage Examples

**Interactive mode (recommended):**
```
/cca:creating-incidents
→ Which server(s) were affected?
→ Which service(s)?
→ ...
→ Creates file with template
```

**Quick mode:**
```
/cca:creating-incidents server1 Apache "high load"
→ Skips questions
→ Creates file immediately with defaults
```

## Template Structure

Created file contains:
```markdown
---
date: 2025-10-10
time: 14:23:15
servers: [server1]
services: [Apache]
severity: medium
status: resolved
tags: [apache, performance, load]
---

# Incident: Brief Description

**Reported:** 2025-10-10 14:23
**Status:** Resolved
**Duration:** [fill in]

## Problem Description
[What happened]

## Investigation
[What you checked]

## Root Cause
[What caused the issue]

## Solution
[What fixed it]

## Prevention
[How to prevent in future]
```

## When to Use

After manually fixing a problem - document it so AI can auto-resolve next time.

---

If a reusable guide would help, recommend `/cca:saving-guides`, but invoke it only when the user
explicitly requests that skill.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
