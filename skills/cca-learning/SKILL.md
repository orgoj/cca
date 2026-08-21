---
name: cca-learning
description: Extract and integrate learnings from current session into project knowledge base
argument-hint: "[optional: source to process]"
allowed-tools: Read(*), Write(*), Edit(*), Glob(*), Grep(*), Bash(*)
---

# Learn - Session-Based Learning

Analyze current session for mistakes, new procedures, and better approaches. Update guides and the project's rules file accordingly.

> **Kam patří kritická pravidla:** každý projekt má svůj rules file — `AGENTS.md`/`CLAUDE.md` (nebo
> dedikovaný critical-rules guide). NEpředpokládej `RULES.md`; over, kde projekt drží pravidla
> (typicky `AGENTS.md`), a piš tam. Postupy a checklisty vždy do `guides/`, ne do rules file.

**Source to process:** $ARGUMENTS

## Steps

### 1. Analysis
**Detect source:**
- **No argument** → Current session context
- **Starts with http/https** → URL to fetch
- **Ends with .md** → File to read
- **Contains "mistake", "error", "fix"** → Mistake/correction to capture
- **Anything else** → Text content to process

**Analyze content** - Extract mistakes, new procedures, better approaches, critical rules.
**Keep only what actually happened** - a lesson comes from a real failure with a real cause. A rule
that "sounds sensible" but was never triggered in the session only dilutes the rules everyone else
has to read. Where an incident file for the failure already exists, reference it; do not create one
just to have an ID.
**Distill before you write** - for each candidate lesson produce a one-line causal template first:
`what failed → why it failed → what actually fixed it`. If the "why" is missing, it is not a lesson
yet: either verify the cause or drop it. Write guides from these lines, not from the raw transcript.
**Search related guides** - Use tantivy2agents search to find guides to update.

### 2. Execution
**Determine update strategy** - Update existing guide, create new, or add to the project rules file (AGENTS.md/CLAUDE.md).
**Apply updates** - Intelligent deduplication (check if info already exists). One rule = one place;
write per `cca-core` → *Written Knowledge: Evidence & Length*.
**Do not regress older lessons** - before editing an existing guide, search for the 2-5 earlier
incidents/guides on the same topic and check the change does not contradict how they were resolved.
If the old rule still holds in a different context (other OS, version, service), branch the guide
instead of rewriting the general rule. If it genuinely conflicts, report the conflict and wait for
approval - never silently reverse a decision someone already made.

### 3. Report
Show what was updated and why.

## Learning Categories

**Critical Rules → project rules file (AGENTS.md / CLAUDE.md):**
- Security violations, data loss risks, breaking production
- Tool misuse causing errors
- Example: "NEVER kill processes without verification"

**Procedures → guides/:**
- Step-by-step procedures for common tasks
- Example: "Domain setup procedure"

**Tips & Tricks → guides/:**
- More efficient commands, useful flags
- Example: "Use grep -a for binary content"

**Server-Specific → the server's guide (`guides/servers/<name>.md`):**
- Configuration details, known issues
- Example: "Apache on server1 has dynamic vhost config"

## Usage Examples

**After user correction:**
```
User: No! You must use grep -a for HTML!
cca-learning "grep -a required for HTML"
→ Adds to project rules file (AGENTS.md)
→ Updates guides/file-analysis.md
```

**After completing task:**
```
# After domain setup
cca-learning
→ Extracts procedure
→ Updates guides/domain-setup.md
```

**From specific incident:**
```
cca-learning incidents/2025-10-14-apache-high-load.md
→ Learns from documented incident
→ Updates relevant guides
```

---

*Capture knowledge immediately after user corrections or completing tasks!*

> **Housekeeping není práce tohoto skillu.** Deduplikace napříč guides, slučování opakovaných
> incidentů a archivace vytěžených záznamů patří do `cca-optimizing-guides` (měsíční kadence).
> Zde se řeší jen zápis lekcí z aktuální session.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
