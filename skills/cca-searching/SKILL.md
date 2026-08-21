---
name: cca-searching
description: Full-text search for CCA guides and incidents using tantivy2agents. Use when searching guides, incidents, knowledge base, or working with tantivy index.
argument-hint: "search keywords"
allowed-tools: Bash(*), Read(*), Glob(*)
---

# CCA Search - Full-Text Search for Guides and Incidents

**Purpose:** Search through CCA knowledge base (guides, incidents, documentation) using full-text search.

**CRITICAL:** Topic search in CCA documentation goes through `tantivy2agents` — never Glob or grep to
find out which guide covers a subject. (Opening a file whose exact path you already know is not
searching: `Read` it directly.)

## Steps

### 1. Analysis
**Determine search intent and keywords:**
- Use **2-4 focused keywords**.
- Include server name if relevant.
- Determine if searching for guides, incidents, or general docs.

### 2. Execution
**Execute search using `tantivy2agents`:**
- **Guides/Docs:** `tantivy2agents search "keywords"`
- **Incidents:** `tantivy2agents search "keywords incident"`
- **Specific Server:** `tantivy2agents search "server_name keywords"`

### 3. Using the results
- Review ranked results (BM25).
- If no results, broaden keywords. If too many, refine them or use `--limit`.
- Read the selected guide in full, then follow only the cross-references that matter for the task —
  no recursive sweep, no separate behavior map.
- **A guide describes intent, not necessarily today's state.** For files you are about to change or
  claims you are about to repeat as fact, open the actual file. Anything the guide labels
  `neovereno`/`assumed` is an open question, not a fact to build on.

## Search Syntax

### Basic Search (Recommended)

**Good examples:**
```bash
tantivy2agents search "docker high load"
tantivy2agents search "nginx ssl error"
tantivy2agents search "mongodb replica lag"
tantivy2agents search "server server1 disk"
```

### Search for Incidents

**Find similar past problems:**
```bash
tantivy2agents search "problem keywords incident" --limit 5
```

### Output Formats

**Text (default):**
```bash
tantivy2agents search "docker"
```

**JSON (for parsing):**
```bash
tantivy2agents search "docker" --format json
```

## Index Management

**How auto-update works:** `tantivy2agents install` registers a **Claude Code hook**
(`PostToolUse` on `Edit|Write|MultiEdit` → `tantivy2agents hook-clear`) in
`.claude/settings.json`. After each edit the hook only **marks the index as outdated** —
it does NOT rebuild. The rebuild happens automatically on the next `search`
(`_ensure_search_index`). There are NO git hooks involved.

### Check Index Status
```bash
tantivy2agents status   # shows "Up to date" / "Out of date" + missing files
```

### Rebuild Index
**Rucni rebuild NENI potreba** — `search` si outdated index prebuduje sam pred hledanim.
Rucni `index` spoustej jen pri troubleshootingu (status hlasi problem, index nelze otevrit):
```bash
tantivy2agents index --force    # force full rebuild (troubleshooting only)
```

### Troubleshooting: search stale / hook missing
If `.claude/settings.json` was deleted (or the hook is gone), the index stops being
marked outdated. Re-register the hook without touching the config, then rebuild:
```bash
tantivy2agents install --no-config   # re-installs the Claude Code hook only
tantivy2agents index                 # rebuild
```

## Archivované incidenty — jak dohledat

Staré vytěžené incidenty se archivují do `incidents/archive/YYYY/` (viz `cca-optimizing-guides`
operace `consolidate-incidents`) a jsou **záměrně mimo full-text index** — aktivní search vrací jen
živé incidenty. **Soubor se ale NEMAŽE a jméno se NEMĚNÍ.**

Když narazíš na odkaz `incidents/<YYYY-MM-DD-...>.md`, který v `incidents/` není:
```bash
ls incidents/archive/*/<YYYY-MM-DD-...>.md      # je tam pod stejnym jmenem
# nebo: git log --all --full-history -- '**/<jmeno>.md'
```
Jméno incidentu je jedinečné (prefix data), takže je vždy dohledatelný — archivace mění jen složku.

## Setup in CCA Project

Run during `cca-setting-up`:
```bash
tantivy2agents install   # creates config + registers the Claude Code hook
```

---

**Remember:** one concept per query, 2-4 words. A long mix of symptom + service + tool sinks the
relevant guide in the ranking — run a separate short search for each guide you need.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
