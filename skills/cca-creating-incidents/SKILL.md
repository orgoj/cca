---
name: cca-creating-incidents
description: Create or update a record in the project's incidents directory for a specific event or substantive session work, including troubleshooting, audits, and analysis without a failure; append new evidence or dated follow-ups to an existing record of the same event or task
argument-hint: "[server] [service] [brief-description]"
allowed-tools: Write(*), Bash(*), Read(*)
---

# Incident-Create - Event and Session Work Documentation

Document a specific event or substantive session work, including audits and analysis without a
failure. Choose the problem or work template to match the task; the incidents directory also holds
work records that do not describe an outage.

**Quick create arguments:** $ARGUMENTS

> **MANDATORY: `cca-core` → *Written Knowledge: Evidence & Length*.** If `cca-core` is not already
> loaded in the active conversation context, read it before writing. Never reload it redundantly.
> An incident is an immutable record — it is never edited into shape later.

## Steps

### 1. Analysis
**NEJDŘÍV OVĚŘ, ZE STEJNÝ INCIDENT UŽ NEEXISTUJE:**
- `tantivy2agents search "klicova slova tematu"` (2-4 slova).
- Existující soubor doplň pouze tehdy, když popisuje stejnou konkrétní událost nebo její pokračování
  (stejné časové okno/problém), nebo stejné konkrétní zadání práce či jeho pokračování.
  Pouhá shoda serveru, služby, symptomu nebo historické podobnosti
  nestačí. Nová událost v jiném čase je samostatný incident, pokud už nemá vlastní rozpracovaný záznam.
- Pokud stejná událost už má incident (i částečný/rozpracovaný, například TODO položku s vlastní
  sekcí), **NEZAKLÁDAT NOVÝ** — otevři a doplň existující soubor novou sekcí/dodatkem s datem;
  nenahrazuj původní záznam.

**NEJDŘÍV OVĚŘ ČASOVOU OSU:**
- Spusť `date` pro aktuální čas
- Použij ověřené timestampy ze session; chybějící klíčové časy si vyžádej nebo označ jako chybějící
  (u poruchy kdy nahlášeno/vyřešeno, u práce relevantní čas provedení či ověření).
- **NIKDY nevymýšlej/neodhaduj časy** — vymyšlený timestamp v incidentu přežije roky a nikdo ho
  jako vymyšlený nepozná. Neznáš čas? Zeptej se, nebo napiš, že chybí.
- **Kdyz user behem konverzace odkazuje na prave provedenou/aktualni akci** ("ted", "prave ted",
  "prave jsem") — spust `date` OKAMZITE v tu chvili, ne az na konci. Neodvozuj cas z drivejsich
  timestampu v konverzaci.

**Collect record details** - Use provided arguments and verified session context; ask only for
missing information needed for the record.
- Event or task, scope, and brief description?
- Relevant server(s) and service(s), if any?
- Verified findings, actions, outcome, and open questions?
- For a problem: severity (critical/high/medium/low) and status
  (resolved/monitoring/investigating), only when supported by the evidence?
- For work without a failure: status (completed/in-progress), as supported by the outcome?

### 2. Execution
**Create file** - in the project's CCA incidents directory: `<cca-root>/incidents/YYYY-MM-DD-brief-description.md`. When CCA lives in a subdir, this is `cca/incidents/`. Verify where existing incidents live and write there — never invent a new top-level `incidents/`.
**Choose and fill the template** - Use the problem template for troubleshooting or the work
template for audits, analysis, and other work without a failure. Keep only applicable metadata
and sections with verified content.

### 3. Output
**Auto-indexed** - Search index updates automatically, no manual action needed.
**Report the path** to the created file.

**Mitigation status** - A mitigation applied after the incident traffic ended is `monitoring`, not
verified `resolved`. Record the deployment timestamp and the exact condition for future verification.

## Incident-specific rules

On top of `cca-core` → *Written Knowledge: Evidence & Length*:

- **Root Cause applies only to a problem and is filled in only when proven.** If its cause remains
  open, record the symptom, collected evidence, and an actionable question marked
  `neovereno — <open question>, over pres: <command/query>`. Omit Root Cause for work without a failure.
- **Duration applies only when relevant and supported by verified start and end times.** Omit it
  otherwise; do not infer outage duration from the session length.
- **`Status:` is the state at the time of writing, not a live state.** Nobody comes back to update
  it. Later work building on an old incident verifies the current state and appends a dated note.
- **Shape:** for a problem, symptom → evidence → what was done → what remains open; for other work,
  task → verified findings → actions taken → outcome and open questions. No narration of the session.
- **Keep only event-specific evidence in the incident; put reusable tool or product behavior in an
  existing guide and link that guide from the incident.**

## Usage Examples

**Interactive mode (recommended):**
```
cca-creating-incidents
→ Which server(s) were affected?
→ Which service(s)?
→ ...
→ Creates a record using the applicable template
```

**Quick mode:**
```
cca-creating-incidents server1 Apache "high load"
→ Uses arguments and verified session context
→ Creates a problem record; asks only for necessary missing information
```

## Template Structure

### Problem event

Use this structure for a problem; omit metadata and headings that do not apply or lack evidence.
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
**Duration:** [only if relevant and verified from start and end times]

## Problem Description
[What happened — observed symptoms only]

## Investigation
[Commands actually run + their real output]

## Root Cause
[Proven cause only; otherwise omit and put the actionable open question under Investigation]

## Solution
[What was actually done, and by whom]

## Prevention
[Only if something concrete was decided. Otherwise omit this section.]
```

### Work without a failure

Use this structure for an audit, analysis, or other substantive task. Add servers or services only
if relevant; omit severity, outage duration, and Root Cause.

```markdown
---
date: 2025-10-10
time: 14:23:15
status: completed
tags: [audit]
---

# Work Record: Brief Description

## Task
[Requested objective and scope]

## Verified Findings
[Evidence actually collected, with sources or commands and their real output]

## Actions Taken
[What was actually done, and by whom; omit if no actions were taken]

## Outcome and Open Questions
[Verified result, limits of the work, and remaining questions with concrete verification steps]
```

Template dates, times, and statuses are examples; replace them with verified values. A completed
audit or analysis does not imply that every finding has been remediated.

Delete every heading you have nothing verified to put under — an empty or speculative section is
worse than a missing one.

## When to Use

When asked to record a specific event or substantive session work in the project's incidents
directory: troubleshooting, an audit, analysis, or a dated follow-up to the same event or task.
Keep reusable procedures in guides and link them from the record.

---

If a reusable guide would help, recommend `cca-saving-guides`, but invoke it only when the user
explicitly requests that skill.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
