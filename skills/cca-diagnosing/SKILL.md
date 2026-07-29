---
name: cca-diagnosing
description: Context-aware troubleshooting with data aggregation
argument-hint: "[server] [symptom]"
allowed-tools: Bash(*), Read(*), Glob(*), Grep(*)
---

# Diagnose - Context-Aware Troubleshooting

AI-powered troubleshooting that aggregates data from multiple sources.

**Server and symptom:** $ARGUMENTS

## Steps

### 1. Analysis
**Load server context** - Read the project's `server-{servername}/SKILL.md` doc (specs, services, known issues); find it via `tantivy2agents search "{servername}"` (location varies per project)
**Parse symptom** - Extract keywords: server, symptom words (slow, high, error, etc.)

### 2. Execution
**Gather current state** - Use `cca-diagnose-gather SERVER "SYMPTOMS"` to get JSON report of system state, services, and recent commands.
**Search similar incidents** - Tantivy search for historical matches

### 3. Diagnostic report
**Correlate data** - Compare current state with historical incidents
**Present diagnosis** - Current state, historical match (with file reference), recommended action.
Any fix/change still requires the standard approval flow — this skill NEVER executes fixes.
Separate what the data shows from what you infer from it, and say which parts are still unverified.

## Data Gathering

**System basics (always):**
- uptime, memory (free -h), disk (df -h), load average

**Conditional service checks (based on keywords):**
- apache/php/web/http → apache2ctl fullstatus
- docker/container → docker ps + stats
- mongodb/mongo/db → service-specific status commands

**Recent commands:**
- Extract from latest log file

## Search Strategy

**Tantivy search:**
- Fast keyword-based search in incidents/

**Combine results:**
- Merge and rank by relevance

## Usage Examples

**Basic diagnosis:**
```
/cca:diagnose server1 "high load"
→ Server1 status:
  Load: 45.2 (CPU: 24 cores) - CRITICAL
  Memory: 89% used
  Recent: Apache processes stuck
→ Similar incident: incidents/2025-09-15-....md (same symptom + service)
→ Suggested action: Check Apache processes (per incident Solution)
```

## Output

Diagnostic report includes:
- Current system state
- Service-specific status
- Historical incident matches (file references — say WHY they match: symptom/service/server)
- Recommended actions (proposal only — execution needs user approval)

**No invented numbers:** never present a "confidence %" or "match %" — you have no mechanism
computing it. State the concrete overlap (same symptom, same service, same server) instead.

---

*Automatically called by `/cca:problem` when no guide found - you rarely need to run this directly.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
