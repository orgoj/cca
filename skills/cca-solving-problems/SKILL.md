---
name: cca-solving-problems
description: Solve any server problem - unified intelligent workflow. Also for security incidents - hack, webshell, backdoor, malware, compromised server.
argument-hint: "\"description of the problem\""
allowed-tools: Bash(*), Read(*), Write(*), Edit(*), Glob(*), Grep(*), TaskCreate(*), TaskUpdate(*)
---

# Problem - Unified Problem Resolution

**PREREQUISITE:** Load `cca-core` for system overview and safety rules.

**The ONLY entry point for solving ANY server problem.**

**Problem description:** $ARGUMENTS

## VŽDY NEJDŘÍV: hledej guide (tantivy-first)

**Nikdy neskákej na server ani nestahuj data před vyhledáním guide.**

```bash
tantivy2agents search "<2-3 keywords>"        # guides + incidents
```

Přečti VŠECHNY relevantní guidy a **řiď se jimi** — projektová specifika (jak se stahují/analyzují
logy, jaké jsou timezone, zakázané vzorce, scénáře výpadků) patří do guidů, ne do tohoto sdíleného
skillu. Typicky existuje projektový log/outage guide (např. `*-outage-patterns`, `*-log-analysis`),
který má konkrétní příkazy a SQL dotazy. Postupuj podle něj.

> ⚠️ Logy bývají už lokálně (DuckDB apod.). **Nestahuj je automaticky** — over to v projektovém
> guide. Auto-download bez tantivy je v řadě projektů přímo zakázaný (přepisuje inkrementální stav).

## Steps

### 1. Analysis
**Load CCA Core (MANDATORY)** - `cca-core`
- Tool selection guide (cca-tmux-cli vs ap)
- Safety rules and best practices

**Tmux screen čti jen při nejasném stavu po předchozím příkazu:**
- `cca-tmux-cli -t SERVER read` použij pouze po dřívějším `run`, který zhavaroval, byl přerušen,
  vypršel mu timeout nebo nevrátil finální marker.
- `read` určuje, zda předchozí příkaz stále běží; není to preventivní krok před novým příkazem.
- Pokud žádný předchozí příkaz nezanechal stav nejasný, spusť dokumentovaný `run` rovnou.

**Load Server Context**
- If server mentioned, read the project's server guide (specs, services, known issues).
  Location varies per project (e.g. `cca/guides/servers/{name}.md`) — find it via
  `tantivy2agents search "{servername}"`. Server docs are guides read with `Read`,
  not skills: `Skill({ skill: "server-{name}" })` does not exist.

**Search VŠECHNY relevantní Guides & Incidents — ne jen jeden!**
- Search guides: `tantivy2agents search "$ARGUMENTS"` — přečti VŠECHNY relevantní výsledky
- Search incidents: `tantivy2agents search "$ARGUMENTS incident" --limit 5`
- **Pokud problém zasahuje víc oblastí** (nginx + boti + cache) → hledej KAŽDOU oblast zvlášť
- Ověř aktuální obsah přímo odkazovaných souborů, skriptů a souvisejících guidů, které
  ovlivňují řešené chování. Stav implementace neodvozuj jen z textu guide.
- ❌ Přečíst jeden guide a rovnou jednat
- ✅ Přečíst všechny relevantní guide, cross-reference, pak navrhnout řešení

**Plán změny**
- Explicitně uveď soubory, které se mají změnit, a relevantní závislosti, jejichž aktuální
  obsah byl ověřen.
- Nevypisuj ani neprocházej nesouvisející cross-reference a nevytvářej vedlejší behavior mapu.

### 2. Execution
**Diagnostic Investigation**
- Logy/metriky analyzuj podle projektového guide nalezeného v kroku 1 (lokální data preferuj před stahováním).
- Use `cca-tmux-cli` for live server diagnostics.
- Present diagnostic report.

**Safety Checks**
- Dangerous operations blocked?
- Peak hours protection?
- Critical servers?

### 3. Documentation
- `cca-creating-incidents` - Document the fix.
- `cca-saving-guides` - Create guide immediately.

Both write per `cca-core` → *Written Knowledge: Evidence & Length*.

**Functional testing of a change is a separate, non-negotiable step** (see the project rules): after
any live change, test behaviour and check error logs. That is a real-world check, not a re-reading
of your own reasoning — do not skip it, and do not replace it with re-reviewing your own output.

## Usage Examples

**Known problem (guide exists):**
```
cca-solving-problems "server1 Apache high load"
→ Found: guides/apache-performance.md (95%)
→ Following guide...
→ Problem resolved!
```

**Similar to past incident:**
```
cca-solving-problems "MongoDB replica lag"
→ Found similar incident: incidents/2025-10-01-....md (same service + symptom)
→ Proposing solution from incident, waiting for user approval...
→ Approved → executing → verified → Problem resolved!
```
(No "auto-resolve" and no invented match percentages — fixes always go through the
standard approval flow, matches are justified by concrete overlap, not a score.)

## NO server parameter needed

AI determines affected server from:
- Explicit mention in description
- Service-to-server mapping (from servers.json)
- Investigation results

## Workflow Commands

Called automatically by `cca-solving-problems`:
- `tantivy2agents search` - Guide/incident search
- `cca-diagnosing` - Multi-source diagnostics
- `cca-creating-incidents` - Incident documentation
- `cca-saving-guides` - Guide creation

---

*One command for everything - AI decides the workflow, you just describe the problem!*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
