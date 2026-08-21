---
name: cca-migrating
description: Skill for migrating CCA systems between repositories. Use when migrating CCA from one repo to another, integrating CCA into Ansible repositories, or consolidating multiple CCA setups.
---

# CCA Migration Skill

Skill for migrating CCA (Claude Code Admin) systems between repositories. Handles various CCA organization patterns and structures.

## Steps

### 1. Analysis
**Source Analysis (MANDATORY)**
1. **Identify CCA root location**: Check `.claude/skills/`, `guides/`, `knowledge/`, `incidents/`, `servers.json`.
2. **Categorize content**: Inventory server skills, guides, incidents, configs.
3. **Detect naming conventions**: Server names in source vs target.

### 2. Execution
**Target Preparation**:
1. Create the directory structure (`cca/guides/`, `cca/incidents/`, `logs/`) — same minimal set as
   `cca-setting-up`, and nothing beyond it.
2. Link the shared `cca-*` skills with `cca-install skills`.

**Content Migration**:
1. **Server docs**: old CCA versions kept them as `.claude/skills/server-*`; today they are guides —
   move them to `cca/guides/servers/<name>.md` and update references.
2. **Guides**: Copy from `guides/` or `knowledge/` to `cca/guides/`, update content references.
3. **Incidents**: Copy to `cca/incidents/` (with `archive/YYYY/` if the source has one), rename
   files/references.

**Configuration**:
1. Server configuration: `.cca-env` (Ansible projects) or `servers.json`.
2. Search index: create `.tantivy2agents.json`, then `tantivy2agents install`.
3. `cca/watchlist.json` only if the source project actually uses `cca-watching`.

### 3. Post-migration checks
Real checks against the source repo and a working target — not a re-reading of your own work:
1. Compare file counts/paths between source and target.
2. Grep the target for leftover source server names.
3. Run `tantivy2agents search` and see that it returns migrated content.
4. Run one safe command to confirm hooks fire.

## CCA Structure Variants

Different CCA repositories organize content differently. **ALWAYS analyze source structure first.**

### Content Location Patterns

| Content Type | Variant A (old) | Variant B | Variant C | Target |
|--------------|-----------------|-----------|-----------|--------|
| Server info | `.claude/skills/server-*` | `servers.json` only | `servers/` directory | `cca/guides/servers/` |
| Guides | `.claude/skills/guide-*` | `guides/` | `knowledge/` | `cca/guides/` |
| Incidents | `incidents/` | `logs/incidents/` | `.claude/incidents/` | `cca/incidents/` |
| Config | `.claude/config/` | root `*.json` files | `config/` | `.cca-env` / `servers.json` |

## Server Name Mapping

### From Ansible Inventory
```bash
# Extract hosts from inventory
grep -E '^\[|^[a-zA-Z]' TARGET/production/hosts | grep -v '^\[' | grep -v '^#'
```

## Reference Replacement Patterns

Always replace these patterns in migrated content:
```bash
# Server names in text
sed -i 's/server1/proweb1/g' FILE

# Server names in paths
sed -i 's|server-server1|server-proweb1|g' FILE
```

## Files to Never Copy

- `.tantivy-data/` - regenerate with `tantivy2agents index`
- `logs/*.log` - local runtime logs
- `.claude/settings.local.json.bak` - backups
- `*.tmp`, `*~` - temporary files


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
