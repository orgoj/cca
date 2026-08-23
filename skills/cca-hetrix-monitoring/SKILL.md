---
name: cca-hetrix-monitoring
description: "This skill should be used when the user asks to check server monitoring status, investigate outages, check uptime, or review blacklist status using HetrixTools."
---

# HetrixTools Monitoring Check

Systematic check of all HetrixTools monitors with structured investigation of any outages.

## Prerequisites

- `cca-curl-secret` for secure credential management (sops-based)
- `jq` and `curl` must be available

## Workflow

### Step 1: Check current status
```bash
cca-hetrix
```

### Step 2: Check outages since last check
```bash
cca-hetrix --outages --since YYYY-MM-DD
```

### Step 3: Create tasks for problematic monitors

**IF outages found:**
- Create a TaskCreate item for each problematic monitor
- Each monitor = separate task for detailed investigation

### Step 4: Investigate each problematic monitor (mark as in_progress)

**Nejdřív rozhodni z přehledu, teprve pak vyjížděj detail.** Přehled ze Step 2 už dává
monitor, čas a délku výpadku — to na většinu rozhodnutí stačí.

- Check if outage is already documented (incidents dir, logs, etc.)
- Match by **DATE + SERVICE** - incident from Oct 8 does not explain outage Oct 15
- **Decision**:
  - Sedí na existující incident (datum + služba) → odkaž incident, mark completed.
    **Detail nevyjížděj.**
  - Nový, nezdokumentovaný výpadek → pokračuj níž

⛔ **`--monitor-outages` a `--monitor-info` pouštěj jen tehdy, když to mění rozhodnutí** —
tedy u nového výpadku, kde potřebuješ typ chyby (timeout / refused / 5xx / keyword) nebo
rozsah lokalit, případně cílovou URL pro dohledání v logu. Detail stojí násobně víc než
přehled; u výpadku, který už má incident, nepřinese nic nového.

- **Typ chyby a rozsah lokalit** (nikdy nepředpokládej — timeout, refused a 5xx mají různé
  příčiny):
  ```bash
  cca-hetrix --monitor-outages "monitor-name" --since YYYY-MM-DD
  ```
  Výstup je seskupený do oken výpadku; `--full` vypíše každou jednotlivou sondu (potřeba
  jen výjimečně).
- **Přesná URL a typ monitoru** — jen když ji budeš hledat v logu:
  ```bash
  cca-hetrix --monitor-info "monitor-name"
  ```
- Hledej přesnou URL z `--monitor-info` v lokálních log datech (dle projektového log guide, např. DuckDB) — **nikdy ne grep na serveru!**

### Step 5: Final summary
- Current status (all UP or issues found)
- Summary of investigated monitors
- New issues requiring action (if any)

## Command Reference

| Command | Description |
|---------|-------------|
| `cca-hetrix` | Quick UP/DOWN check (default) |
| `cca-hetrix --down` | Show what's currently down |
| `cca-hetrix --all` | Show all monitors with uptime durations |
| `cca-hetrix --response-times` | Show response times per location |
| `cca-hetrix --outages` | Recent outages (last 24h) |
| `cca-hetrix --outages --since 7d` | Outages last 7 days |
| `cca-hetrix --outages --since 12h --until 6h` | Outages in time range |
| `cca-hetrix --monitor-info "name"` | Monitor details incl. target URL |
| `cca-hetrix --monitor-outages "name"` | Outage history grouped into outage windows |
| `cca-hetrix --monitor-outages "name" --full` | ... one line per probe (rarely needed) |
| `cca-hetrix --blacklist` | Email blacklist overview |
| `cca-hetrix --blacklist-ip 203.0.113.10` | Blacklist detail for IP |

## Critical Rules

- **NEVER use `--monitor-outages` without monitor name** - causes error
- **Use `--outages --since DATE`** for overview of all outages
- **Match incidents by DATE + SERVICE** - don't assume old incident explains new outage
- Time formats: `YYYY-MM-DD`, or relative: `12h`, `7d`, `30m`

## Projektové vzorce (429/rate-limit, false alarmy)

Význam 429/timeout vzorců je projektový — před vyhodnocením outage vždy
`tantivy2agents search "hetrix 429"` (nebo obdobně) v projektových guides.


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
