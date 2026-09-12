---
name: cca-optimizing-guides
description: "Monthly knowledge-base maintenance: find gaps and duplicates, improve guides, consolidate incidents, and clean the operational watchlist"
argument-hint: "[optimize|analyze-gaps|suggest-improvements|find-duplicates|suggest-links|consolidate-incidents|clean-watchlist]"
allowed-tools: Bash(*), Read(*), Write(*), Edit(*), Glob(*), Grep(*)
---

# Guide Optimize - Knowledge Base Maintenance

Monthly maintenance tool to keep knowledge base clean, complete, and optimized.

**Operation:** $ARGUMENTS

## Steps

### 1. Analysis
**Analyze repositories:** `incidents/`, `guides/`, and the project watchlist.
**Identify goals:**
1. **Find gaps** - Repeated incidents without guides
2. **Suggest improvements** - Missing info in existing guides
3. **Find duplicates** - Overlapping content to merge
4. **Suggest links** - Missing cross-references
5. **Consolidate incidents** - Fold recurring incident patterns into a playbook guide, then archive the
   vytěžené (mined) incidents so the active set stays small and searchable
6. **Clean watchlist** - Merge work that is completed by one intervention, close obsolete or already
   completed items, and normalize duplicate `area` names

### 2. Execution
**Run operations:**
- `analyze-gaps`: Cluster incidents by frontmatter `tags:` (plus `servers:`/`services:`) and by
  `tantivy2agents search` on the recurring symptom; a cluster of ≥2 incidents with the same root
  cause and no playbook guide covering it is a gap. Do not cluster by filename or by date.
- `suggest-improvements`: Compare guides with recent incidents to find missing information.
  **Includes stale-guide audit:** freshness is judged from git history (`git log -1` date of the
  guide's last meaningful change), NOT from any changelog section inside the guide. Any guide whose
  last change is older than ~6 months AND whose topic overlaps a newer guide → compare against the
  newer guide + recent incidents; if it contradicts them, rewrite it as a thin router to the current
  guides (or fold it in). Rationale: a stale playbook once survived 7 months while giving advice
  (UA-version bot rule, geo-block) that newer guides explicitly forbid because it caused outages.
- `find-duplicates`: Identify guides covering similar topics that could be merged.
  **Merge nesmí ubrat znalost:** před sloučením vypiš řádky, které jsou JEN v rušeném guide, a ověř,
  že všechny jsou v cílovém. Rušené místo nemaž — nech z něj tenký router na cílový guide.
- `suggest-links`: Find related guides that should reference each other.
- `consolidate-incidents`: Cluster recurring incidents, fold their pattern into the relevant project
  playbook guide, then archive the mined incident files. See dedicated section below.
- `clean-watchlist`: Audit active and idle watchlist items, propose merges and closures, and normalize
  duplicate `area` names. See dedicated section below.

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
cca-optimizing-guides optimize
→ Runs all checks
→ Reports findings (one line each)
→ Asks for approval to apply changes
```

**Specific checks:**
```
cca-optimizing-guides analyze-gaps
→ Finds incidents without guides

cca-optimizing-guides suggest-improvements
→ Analyzes guides vs recent incidents

cca-optimizing-guides consolidate-incidents
→ Najde VSECHNY incidenty stejneho problemu (e.g. 15× scraper outage)
→ Do nejnovejsiho (head) incidentu prida retez referenci na predchozi vyskyty
→ Slozi pattern do playbook guide (prida radky pokud chybi)
→ Navrhne archivaci starsich do incidents/archive/YYYY/ (ceka na souhlas)

cca-optimizing-guides clean-watchlist
→ Najde položky, které patří do jednoho zásahu, jsou hotové/zbytečné nebo používají
  duplicitní názvy area
→ Navrhne konkrétní sloučení, uzavření a přejmenování (provedení čeká na souhlas)
```

## Operation: clean-watchlist

The watchlist is an operational register, not an archive of every idea. Keep its active and idle
set small enough that related work is visible and can be scheduled as one intervention.

### Analysis

1. Run `date +%Y-%m-%d\ %H:%M`, then run `cca-watchlist list --all --json` from the project root.
   Save the complete JSON output to a temporary file and inspect its structure with `yq` before
   querying it. A missing-watchlist error means the working directory is wrong; it does not mean
   there is nothing to clean.
2. Review active and idle items against their `refs`, incident/guide state, and git history. Do not
   infer completion from age alone.
3. Propose a merge only when the items will genuinely be completed by one intervention: they refer
   to the same incident or change, require the same operational `window`, and touch the same primary
   file or tightly coupled files. Similar wording or a shared `area` alone is not enough.
4. Propose `done` when referenced work is demonstrably complete, the underlying incident is
   resolved with no remaining follow-up, or the task has lost its purpose. Record the evidence in
   the report. Never use `remove`; `done` preserves history.
5. Detect `area` variants that denote the same subsystem (case, punctuation, abbreviations, or old
   names). Choose one existing, clear canonical value; do not merge genuinely distinct scopes.

### Report and apply

- Report each proposed change on one line: affected IDs, evidence, and exact action. For merges,
  name the surviving item and list the fields/refs that will be preserved. For area normalization,
  show `old → canonical` and every affected ID.
- Ask for approval before changing the watchlist; cleanup can reschedule or hide operational work.
- After approval, mutate only through `cca-watchlist`: update the surviving item with `edit`, preserve
  all distinct refs and actionable context, mark absorbed or completed items with `done`, and rename
  areas with `edit --area`. Never hand-edit `watchlist.json`.
- Re-run `cca-watchlist list --all --json` and verify every approved ID: exactly one survivor per
  merged group, no lost refs or next actions, intended items are `done`, and normalized areas no
  longer have aliases. Report counts before and after plus any item left unchanged due to ambiguity.

`optimize` includes this operation as part of the monthly run.

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
- **Každý archivovaný incident musí mít alespoň jeden odkaz z aktivního souboru** (head incidentu
  nebo tematického guide). Archiv není v aktivním indexu, takže incident bez odkazu je neviditelný.
  Odkaz z jiného archivovaného souboru tento invariant nesplňuje; počítá se jen aktivní head nebo guide.
  Samostatný incident bez odkazu nearchivuj, nebo na něj nejdřív odkaž z tematického guide.
- **Jeden cluster = právě jeden aktivní head.** Všichni ostatní členové clusteru musí být archivovaní;
  konsolidace není dokončená, pokud v aktivním `<incidents>/` zůstanou dva členové stejného clusteru.
- **Křížové odkazy NEŘEŠ — nejsou překážka.** Incident má jedinečné jméno s datem
  (`YYYY-MM-DD-...md`), které se archivací NEMĚNÍ — mění se jen složka. Odkaz na archivovaný incident
  zůstává platný: když ho nenajdeš v `incidents/`, je v `incidents/archive/YYYY/` pod stejným jménem.
  Odkazy proto piš jen jako jméno souboru a při archivaci je v jiných souborech NEPŘEPISUJ.
  Proto **NEvyřazuj incidenty z archivace jen proto, že na ně něco odkazuje** (to bylo zbytečné omezení).
  Resolver konvenci popiš/over v `cca-searching` (viz tam).

### Postup
1. **Cluster — najdi VŠECHNY incidenty stejného problému.** Ne jen pár podobných: projeď `tantivy2agents
   search` na víc formulací, frontmatter `tags:`, klíčová slova v názvu. Sestav úplný seznam výskytů
   seřazený podle data (od nejstaršího). Cluster = ≥2 incidenty se stejnou root cause.
2. **Vyber „head" = nejnovější incident clusteru** (zůstane aktivní, nearchivuje se). Ostatní (starší)
   jsou určení k archivaci.
3. **Do head incidentu přidej řetěz referencí** — sekce `## Předchozí výskyty` (nebo doplň existující
   „Related incidents") se seznamem VŠECH starších výskytů, od nejnovějšího. Reference piš VŽDY jen
   jako jméno souboru (`YYYY-MM-DD-nazev.md`), NIKDY s prefixem `archive/YYYY/` ani `cca/incidents/`:
   ```markdown
   ## Předchozí výskyty (stejný problém)
   - 2026-04-17 — 2026-04-17-server1-outage-scraper-shop-a.md — botnet z ASN X, blok /22
   - 2026-03-27 — 2026-03-27-server1-outages-scraper-shop-b.md — ASN Y, blok net_range
   - 2025-10-03 — 2025-10-03-dc-scraper-attack-server1.md — první výskyt
   ```
   Tím je celá historie proklikatelná z jednoho místa bez ohledu na to, zda krok archivace proběhne.
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
6. **Archivuj starší členy** — před přesunem zkontroluj, zda některý archivovaný člen sám nese řetěz
   odkazů na starší výskyty; všechny tyto položky nejdřív přenes do řetězu aktivního headu clusteru.
   Teprve potom použij `git mv <incident> <incidents>/archive/YYYY/`. Head zůstává aktivní a odkazuje
   na ně. Křížové odkazy NEŘEŠ jako překážku (viz Pravidla).
7. **Reindex** — `tantivy2agents index` po přesunech. (Výjimka z pravidla „index ručně nespouštět":
   `git mv` jde přes Bash, edit-hook `PostToolUse` na Edit|Write se nespustí, index by zůstal stale.)
8. **Ověření** — spusť až po všech přesunech celé schválené dávky, ne po jednotlivých přesunech.
   Porovnej seznam přesunutých souborů s odkazy ze všech aktivních head incidentů a guides: každý
   archivovaný incident musí mít alespoň jeden aktivní odkaz. Ověř také, že v aktivním
   `<incidents>/` zůstal pro každý konsolidovaný cluster právě jeden head a že žádný odkaz neobsahuje
   `archive/YYYY/` ani `cca/incidents/`; odkazy musí používat jen jméno souboru.

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
