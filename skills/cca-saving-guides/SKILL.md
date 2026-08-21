---
name: cca-saving-guides
description: Automatically save solved issue as systematic guide
argument-hint: "[optional: guide focus]"
allowed-tools: Read(*), Write(*), Edit(*), Glob(*), Grep(*), Bash(*)
---

# Guide Save - Auto-capture Solved Issue

Analyze conversation and create structured guide for solving similar issues in the future.

**Guide focus:** $ARGUMENTS

> **MANDATORY: `cca-core` → *Written Knowledge: Evidence & Length*.** Read it before writing.

## Steps

### 1. Analysis
**Analyze conversation** - Extract problem, diagnostics, solution, mistakes
**Search existing guides** - Use tantivy2agents search to check for similar guides

### 2. Execution
**Determine action** - Create new guide or update existing one
**Structure content** - Organize into standard guide sections
**Save to guides/** - Create `guides/lowercase-guide-name.md` with YAML frontmatter

### 3. Follow-up
**Update server docs** - If server-specific, update relevant server skills

## Guide Structure

Created guides include:
- **YAML frontmatter** - servers: [list], tags: [list]
- **Symptoms** - How to recognize the issue
- **Diagnostic steps** - Commands and procedures
- **Solution** - Step-by-step resolution
- **Common traps** - Warnings about mistakes
- **Prevention** - How to avoid the issue
- **Related incidents** - File references only (not detailed content)

**The list is a menu, not a checklist — include a section only if you have verified content for it.**
Four solid sections beat eight where half are guesses.

## Findability conventions (tantivy must find guide on 1st try with 1 word)

Goal: `tantivy2agents search "toolname"` → guide is the FIRST result.

- **Filename** MUST contain the tool/technology keyword (`duckdb-log-analysis.md`, not `log-analysis.md`).
- Frontmatter `tags:` MUST contain the keyword (`tags: [duckdb, ...]`).
- Frontmatter `name:` MUST start with the keyword (`name: duckdb-log-analysis`).
- After writing, TEST: `tantivy2agents search "toolname"` → guide is first result.

**Freshness:** the guide must be current AS A WHOLE — on every edit update or remove
anything the change makes stale; no dated changelog section is kept (history lives in git).
When verifying live data (versions, limits, ports), you may note `(overeno YYYY-MM-DD)`
inline so the reader sees how fresh the info is.

## Usage Examples

**After solving problem:**
```
cca-saving-guides
→ Analyzes session
→ Suggests: guides/apache-performance.md
→ Creates structured guide
```

**With focus:**
```
cca-saving-guides "Focus on Docker networking troubleshooting"
→ Emphasizes Docker network aspects in guide
```

## Critical Rules

**Server commands format:**
- Use pure server commands: `sudo cat /var/lib/file`
- CCA utility scripts OK: `cca-server-status server1` (from PATH)
- Never remote wrappers in guides: `cca-run-on-server server1 "command"`

**Context efficiency:**
- NO duplicate command sections
- NO redundant information
- NO "Real Example" sections - use Related Incidents instead
- Each command appears once in appropriate place

**Related incidents:**
- List file references ONLY: `incidents/filename.md - brief description`
- NO detailed incident content in guides

**Konsolidace do jedne guide:**
- Kdyz se obsah presouva do nove/existujici guide, stare misto dostane JEN odkaz
  (`→ cesta/k/guide.md`), NIKDY zkracenou verzi pravidla — i jedna prepsana veta je
  duplicita, ktera se casem rozejde s originalem.

---

*Create guides immediately after fixing - don't wait for pattern to emerge!*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
