---
name: cca-asking
description: Natural language interface for server administration
argument-hint: "\"question in natural language\""
allowed-tools: Bash(*), Read(*), Glob(*), Grep(*), mcp__*
---

# Ask - Conversational Admin Interface

Ask questions in natural language, get intelligent answers.

**Question:** $ARGUMENTS

## Steps

### 1. Analysis
**Parse natural language question** - Detect language and intent.
**Identify required data** - Determine what information is needed.

### 2. Execution
**Execute appropriate commands:**
- Use `cca-server-info SERVER` for server specifications.
- Use `cca-check-domain DOMAIN` for DNS/routing checks.
- Run server commands, search files, check status for other queries.
**Interpret results** - Analyze output and provide context.

### 3. Answer
Respond in the user's language, naturally and briefly — answer first, supporting detail after.
Answer only from data you actually retrieved. If a command did not run or returned nothing usable,
say what is missing instead of filling the gap with a plausible answer.

## Supported Intents

**Server health:** "is MongoDB healthy?", "is server1 running?"
**Disk space:** "which server has most free space?"
**Incidents:** "when was the last incident on server1?"
**Safety checks:** "can I safely restart server1?"
**Server info:** "give me info about server1"
**General questions:** Natural language queries about infrastructure

## Usage Examples

**Health check:**
```
cca-asking "is MongoDB healthy?"
→ MongoDB is healthy. Primary: server1, all replicas responding.
```

**Disk space:**
```
cca-asking "which server has most free space?"
→ Server3 has most free space (8.2TB free of 12TB).
```

**Safety check:**
```
cca-asking "can I safely restart server1?"
→ NO - server1 is NOT safe to restart:
  - It's MongoDB PRIMARY (failover needed)
  - Running 15 Docker services
  - Currently peak hours (9-17)
```

**Recent incidents:**
```
cca-asking "when was the last incident on server1?"
→ Last incident on server1: 2025-10-01 - Apache high load
```

## Output

Natural language answer with:
- Direct answer to the question
- Supporting details and context
- Actionable information when relevant
- Follow-up suggestions if applicable

---

*Natural language interface for quick infrastructure queries - no need to remember commands or syntax.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
