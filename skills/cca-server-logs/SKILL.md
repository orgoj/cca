---
name: cca-server-logs
description: Analyza serverovych logu — obecna pravidla. Projektove detaily (nastroje, formaty, timezone, schema) jsou VZDY v projektovem log guide; najdi ho pres tantivy2agents jako prvni krok.
allowed-tools: Bash(*), Read(*), Grep(*)
---

# Server Logs — obecny postup

Kazdy projekt ma JINE logy: jine servery, formaty radku, timezone, jine nastroje — nekde lokalni
DB pipeline (napr. DuckDB), jinde se vse resi primo na serverech. Tenhle skill nese jen
univerzalni pravidla; **konkretni postup je VZDY v projektovem guide, ne tady.**

## 1. Najdi projektovy log guide (POVINNY prvni krok)

```bash
tantivy2agents search "log analysis"      # typicky *-log-analysis.md, *-outage-patterns.md
tantivy2agents search "<server> logy"
```

Ridit se guidem — skripty, cesty, SQL, timezone tabulky jsou tam. **Bez guide se postup
nevymysli** — zeptej se usera.

## 2. Univerzalni pravidla (plati vsude)

- **Lokalni kopie/DB pred zivym ctenim na serveru.** Ma-li projekt lokalni log pipeline
  (fetch/import), NEspoustej ji automaticky — data uz byvaji lokalne; obnovu jen kdyz user rekne,
  data chybi, nebo je cerstvy incident.
- **Hotove analyza skripty projektu PRED rucnim SQL/grep** — a jejich vystup NIKDY nekratit
  `head`/`tail` (okna a top-N jsou navrzena k celkovemu cteni).
- **Format a timezone logu NIKDY nepredpokladej** — over v guide; per-server rozdily
  (UTC vs lokalni cas, jina jmena sloupcu/poli) jsou bezne a spatny prepocet = spatny zaver.
- **Zivy log na serveru cti cilene** (`grep -c`, `grep ... | tail -10`), zadny `tail -100`
  a cteni nahodnych radku — pravidla v `cca-core`. Pri zivem incidentu negrepuj serverove logy,
  pokud existuje lokalni kopie.
- **Rotaci/mazani logu over driv, nez prohlasis "data chybi"** — mezera pres rotacni hranici
  byva ocekavana vlastnost, ne bug.
- **Exporty/mezivysledky do `tmp/` V PROJEKTU** (gitignored), nikdy do systemoveho `/tmp`.
- Cerstvy request nemusi byt hned v logu (buffer/flush) — "neni v logu" over az po chvili /
  po importu, ne sekundu po requestu.

## 3. Zavery = data

Tvrzeni o tom, kam request sel / co delal backend, podloz dotazem do spravne vrstvy logu
(proxy pohled != backend realita). Nemas-li overeno, rekni "neovereno".


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
