---
name: cca-optimizing-guides
description: Optimize and evolve knowledge base - monthly maintenance
argument-hint: "[optimize|analyze-gaps|suggest-improvements|find-duplicates|suggest-links|suggest-patterns|consolidate-incidents]"
allowed-tools: Task(*), Bash(*), Read(*), Write(*), Edit(*), Glob(*), Grep(*)
---

# Guide Optimize - Knowledge Base Maintenance

Monthly maintenance tool to keep knowledge base clean, complete, and optimized.

**Operation:** $ARGUMENTS

## Steps

### 1. Analysis
**Analyze repositories:** `incidents/`, `guides/`, and `logs/`.
**Identify goals:**
1. **Find gaps** - Repeated incidents without guides
2. **Suggest improvements** - Missing info in existing guides
3. **Find duplicates** - Overlapping content to merge
4. **Suggest links** - Missing cross-references
5. **Propose patterns** - New auto-approval patterns from logs
6. **Consolidate incidents** - Fold recurring incident patterns into a playbook guide, then archive the
   vytěžené (mined) incidents so the active set stays small and searchable

### 2. Execution
**Run operations:**
- `analyze-gaps`: Use `cca-learn-analyzer` to find repeated incidents and patterns.
- `suggest-improvements`: Compare guides with recent incidents to find missing information.
  **Includes stale-guide audit:** freshness is judged from git history (`git log -1` date of the
  guide's last meaningful change), NOT from any changelog section inside the guide. Any guide whose
  last change is older than ~6 months AND whose topic overlaps a newer guide → compare against the
  newer guide + recent incidents; if it contradicts them, rewrite it as a thin router to the current
  guides (or fold it in). Rationale: a stale playbook once survived 7 months while giving advice
  (UA-version bot rule, geo-block) that newer guides explicitly forbid because it caused outages.
- `find-duplicates`: Identify guides covering similar topics that could be merged.
- `suggest-links`: Find related guides that should reference each other.
- `suggest-patterns`: Analyze logs for safe read-only commands to add to auto-approval.
- `consolidate-incidents`: Cluster recurring incidents, fold their pattern into the relevant project
  playbook guide, then archive the mined incident files. See dedicated section below.

### 3. Report
- One line per finding: what, where, proposed action. Detail only where it is needed to decide.
- Ask for approval to apply changes (merges, new guides, links).
- **Prune while you are in there:** unverified claims, speculative causes, duplicated rules and
  padding are findings too — measured against `cca-core` → *Written Knowledge: Evidence & Length*.
  Reversing an existing decision, however, needs evidence and the user's approval: flag the
  conflict, do not resolve it yourself.

## Usage Examples

**Full optimization (monthly):**
```
/cca:optimizing-guides optimize
→ Runs all checks
→ Reports findings (one line each)
→ Asks for approval to apply changes
```

**Specific checks:**
```
/cca:optimizing-guides analyze-gaps
→ Finds incidents without guides

/cca:optimizing-guides suggest-improvements
→ Analyzes guides vs recent incidents

/cca:optimizing-guides consolidate-incidents
→ Najde VSECHNY incidenty stejneho problemu (e.g. 15× scraper outage)
→ Do nejnovejsiho (head) incidentu prida retez referenci na predchozi vyskyty
→ Slozi pattern do playbook guide (prida radky pokud chybi)
→ Navrhne archivaci starsich do incidents/archive/YYYY/ (ceka na souhlas)
```

## Operation: consolidate-incidents

Recurring near-duplicate incidents (same root cause, different victim/date) pile up and dilute search.

**Jádro operace = najít VŠECHNY incidenty stejného problému a propojit je do řetězu:**
nejnovější (aktivní) incident clusteru dostane sekci s **referencemi na všechny předchozí výskyty**.
Tím vznikne jeden „head" incident, ze kterého se proklikáš celou historií problému — a teprve to
dělá archivaci starších bezpečnou a smysluplnou. Znalost se navíc složí do playbook guide; incidenty
zůstávají jako immutable záznam — **archivuj, nikdy nemaž**.

### Pravidla
- **NIKDY nemaž incident.** Je to auditní/historický záznam. Konsoliduje se znalost, ne soubory.
- Archivuj přes `git mv` do `<incidents>/archive/YYYY/` (rok dle data incidentu). NEpřesouvej ručně.
- Archiv se **vyřadí z aktivního tantivy indexu** (viz Setup níže) — historie zůstává v gitu i na disku.
- Než cokoli archivuješ, **pattern musí být v playbooku** — jinak by se znalost ztratila.
- **Křížové odkazy NEŘEŠ — nejsou překážka.** Incident má jedinečné jméno s datem
  (`YYYY-MM-DD-...md`), které se archivací NEMĚNÍ — mění se jen složka. Odkaz na archivovaný incident
  zůstává platný: když ho nenajdeš v `incidents/`, je v `incidents/archive/YYYY/` pod stejným jménem.
  Proto **NEvyřazuj incidenty z archivace jen proto, že na ně něco odkazuje** (to bylo zbytečné omezení).
  Resolver konvenci popiš/over v `cca-searching` (viz tam).

### Postup
1. **Cluster — najdi VŠECHNY incidenty stejného problému.** Ne jen pár podobných: projeď `tantivy2agents
   search` na víc formulací, frontmatter `tags:`, klíčová slova v názvu. Sestav úplný seznam výskytů
   seřazený podle data (od nejstaršího). Cluster = ≥2 incidenty se stejnou root cause.
2. **Vyber „head" = nejnovější incident clusteru** (zůstane aktivní, nearchivuje se). Ostatní (starší)
   jsou kandidáti na archiv.
3. **Do head incidentu přidej řetěz referencí** — sekce `## Předchozí výskyty` (nebo doplň existující
   „Related incidents") se seznamem VŠECH starších výskytů, od nejnovějšího:
   ```markdown
   ## Předchozí výskyty (stejný problém)
   - 2026-04-17 — server1-outage-scraper-shop-a.md — botnet z ASN X, blok /22
   - 2026-03-27 — server1-outages-scraper-shop-b.md — ASN Y, blok net_range
   - 2025-10-03 — archive/2025/dc-scraper-attack-server1.md — první výskyt
   ```
   Uveď cestu vč. `archive/YYYY/` u už archivovaných. Tím je celá historie proklikatelná z jednoho místa.
4. **Slož znalost do guides — POVINNÝ výstup konsolidace, ne jen kontrola.** Konsolidace typicky
   guides MĚNÍ; archivace je bezpečná teprve, když je znalost zapsaná:
   - **Playbook** (`*-outage-patterns`, `*-troubleshooting`): symptom→příčina→řešení každého clusteru.
     Chybí řádek? Přidej. Playbook neexistuje → gap, nejdřív `analyze-gaps` / vytvoř ho.
   - **Tematické guides** (blokace IP, bot detekce, cache, log-analýza…): diagnostické kroky, SQL
     dotazy, pravidla a rozhodnutí z vytěžovaných incidentů, které v guides chybí — doplň tam, kam
     tematicky patří, NE všechno do jednoho playbooku.
   - Řiď se konvencemi `cca-saving-guides`: findability, guide aktuální jako celek (žádný changelog
     v guide, historie je v gitu), žádná duplikace (starší místo dostane jen odkaz).
   - Konsolidace bez jediné změny guide = podezřelá: buď je opravdu vše už zapsané (ověř a řekni to
     explicitně v reportu), nebo byl tento krok přeskočen.
5. **Report + souhlas** — ukaž: head incident, řetěz referencí, které starší incidenty se archivují,
   které guides se změnily a jak (playbook řádky + tematické doplňky). **Čekej na souhlas**
   (hromadná operace).
6. **Archivuj starší členy** — `git mv <incident> <incidents>/archive/YYYY/`. Head zůstává aktivní a
   odkazuje na ně. Velmi čerstvé výskyty (< ~3 měsíce) můžeš nechat aktivní i tak — neztratí se, head
   na ně ukazuje. Křížové odkazy NEŘEŠ jako překážku (viz Pravidla).
7. **Reindex** — `tantivy2agents index` po přesunech. (Výjimka z pravidla „index ručně nespouštět":
   `git mv` jde přes Bash, edit-hook `PostToolUse` na Edit|Write se nespustí, index by zůstal stale.)

### Setup: vyřadit archiv z indexu (jednorázově)
V `.tantivy2agents.json` přidej do `index_dirs`:
```json
{ "path": "cca/incidents/archive", "exclude": true }
```
(uprav cestu dle umístění CCA v projektu). Tím aktivní search vrací jen živé incidenty; archiv je
dohledatelný přes git/grep, když je potřeba.

### Kadence
Měsíčně, nebo když denní `cca-watching` napočítá N podobných incidentů za měsíc → flag „spusť
consolidate-incidents". Cíl: aktivní `incidents/` zůstává malý, playbook roste.

---

*Run monthly or after series of incidents to maintain knowledge quality.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
