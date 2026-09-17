---
name: cca-creating-incidents
description: Create or update incident documentation for a specific problem event, including appending new evidence or a dated follow-up to an existing incident
argument-hint: "[server] [service] [brief-description]"
allowed-tools: Write(*), Bash(*), Read(*)
---

# Incident-Create - Manual Incident Documentation

Create structured incident documentation after manually resolving a problem.

**Quick create arguments:** $ARGUMENTS

> **MANDATORY: `cca-core` → *Written Knowledge: Evidence & Length*.** If `cca-core` is not already
> loaded in the active conversation context, read it before writing. Never reload it redundantly.
> An incident is an immutable record — it is never edited into shape later.

## Steps

### 1. Analysis
**NEJDŘÍV OVĚŘ, ZE STEJNÝ INCIDENT UŽ NEEXISTUJE:**
- `tantivy2agents search "klicova slova tematu"` (2-4 slova).
- Existující soubor doplň pouze tehdy, když popisuje stejnou konkrétní událost nebo její pokračování
  (stejné časové okno/problém). Pouhá shoda serveru, služby, symptomu nebo historické podobnosti
  nestačí. Nová událost v jiném čase je samostatný incident, pokud už nemá vlastní rozpracovaný záznam.
- Pokud stejná událost už má incident (i částečný/rozpracovaný, například TODO položku s vlastní
  sekcí), **NEZAKLÁDAT NOVÝ** — otevři a doplň existující soubor novou sekcí/dodatkem s datem;
  nenahrazuj původní záznam.

**NEJDŘÍV OVĚŘ ČASOVOU OSU:**
- Spusť `date` pro aktuální čas
- Zeptej se uživatele na klíčové timestampy (kdy nahlášeno, kdy vyřešeno)
- **NIKDY nevymýšlej/neodhaduj časy** — vymyšlený timestamp v incidentu přežije roky a nikdo ho
  jako vymyšlený nepozná. Neznáš čas? Zeptej se, nebo napiš, že chybí.
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

### 3. Output
**Auto-indexed** - Search index updates automatically, no manual action needed.
**Report the path** to the created file.

**Mitigation status** - A mitigation applied after the incident traffic ended is `monitoring`, not
verified `resolved`. Record the deployment timestamp and the exact condition for future verification.

## Incident-specific rules

On top of `cca-core` → *Written Knowledge: Evidence & Length*:

- **Root Cause is filled in only when it was proven.** No proof → symptom, evidence collected, and
  `Root Cause: neovereno — <open question>, over pres: <command/query>`.
- **`Status:` is the state at the time of writing, not a live state.** Nobody comes back to update
  it. Later work building on an old incident verifies the current state and appends a dated note.
- **Shape:** symptom → evidence → what was done → what remains open. No narration of the debugging
  journey.
- **Keep only event-specific evidence in the incident; put reusable tool or product behavior in an
  existing guide and link that guide from the incident.**

## Usage Examples

**Interactive mode (recommended):**
```
cca-creating-incidents
→ Which server(s) were affected?
→ Which service(s)?
→ ...
→ Creates file with template
```

**Quick mode:**
```
cca-creating-incidents server1 Apache "high load"
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
[What happened — observed symptoms only]

## Investigation
[Commands actually run + their real output]

## Root Cause
[Proven cause. Not proven? Write: neovereno — <open question>, over pres: <command>]

## Solution
[What was actually done, and by whom]

## Prevention
[Only if something concrete was decided. Otherwise omit this section.]
```

Delete every heading you have nothing verified to put under — an empty or speculative section is
worse than a missing one.

## When to Use

After manually fixing a problem - document it so AI can auto-resolve next time.

---

If a reusable guide would help, recommend `cca-saving-guides`, but invoke it only when the user
explicitly requests that skill.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
