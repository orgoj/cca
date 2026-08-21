---
name: cca-setting-up
description: Setup CCA (Cyber-CLI Admin) system in project for server management, incident resolution, knowledge management. Use when initializing CCA system, setting up server management, or preparing project for infrastructure administration. Creates minimal required structure - guides, incidents, logs, and search index.
---

# CCA System Setup

Complete infrastructure administration system setup - server management, incident resolution, knowledge base, and learning.

## Steps

### 1. Check Existing Setup
**Verify what already exists using `cca-doctor`:**
- Run `cca-doctor` to see current status.
- It checks for `cca/guides/`, `cca/incidents/`, `logs/`, `.cca-env` (or legacy `.env`), and `tantivy2agents`.

### 2. Create Core Directories
**Create only what's missing:**
- `cca/guides/` - Knowledge base guides (if missing)
- `cca/incidents/` - Incident documentation (if missing)
- `logs/` - Session logs from cca-tmux-cli (if missing)

**Note:** Project root `logs/`, NOT `cca/logs/` - cca-tmux-cli uses `LOG_DIR="logs"`

### 3. Setup Full-Text Search
**Configure tantivy2agents:**
- Create `.tantivy2agents.json` if missing
- Configure to index: `cca/`, playbooks, documentation
- Run `tantivy2agents install` to build index

### 4. Update Documentation
**CCA documentation is handled via skills:**
- No project-specific CCA documentation is needed in `CLAUDE.md`.
- Ensure `cca-core` skill is linked.
- The `cca-doctor` tool verifies the environment without needing `CLAUDE.md` instructions.

### 5. Server Configuration
**Ask user about their setup:**
- How are servers configured? (Ansible inventory, .cca-env, servers.json, other)
- Connection method? (cca-tmux-cli, ssh, ansible ad-hoc)
- Help user set up appropriate configuration file

**Common patterns:**
- **Ansible projects**: Use `.cca-env` with `TMUX_SESSION_SERVERS` variable (legacy `.env` still works)
- **Standalone CCA**: Use `servers.json` or similar
- **Other**: User-specific configuration

## What Gets Created

### Directory Structure (Minimal Setup)
```
cca/
├── guides/              # Knowledge base guides
└── incidents/           # Incident documentation
logs/                    # Session logs (cca-tmux-cli LOG_DIR="logs")
.tantivy-data/           # Search index (created by tantivy2agents)
```

### Configuration Files
```
.tantivy2agents.json     # Full-text search configuration
.cca-env or servers.json # Server configuration (project-specific)
```

**NOT created (optional/deprecated):**
- ❌ `cca/knowledge/` - not used in practice
- ❌ `cca/logs/` - cca-tmux-cli uses root `logs/` directory
- ❌ `cca/watchlist.json` - monitoring not universally used; create it (template in
  `cca-setting-up/templates/`) only when the project runs `cca-watching`
- ❌ `RULES.md` - safety rules in skills
- ❌ `CLAUDE.md` CCA section - instructions are in `cca-core` skill

## Post-Setup Instructions

Run `cca-doctor` to verify everything is correct.

Show user:
```
CCA Setup Complete!

Next steps:
1. Load the cca-core skill (mandatory before ANY server work)
2. Run diagnostic: cca-doctor
3. Search guides: tantivy2agents search "keywords" (see cca-searching skill)
4. Problem workflow: cca-solving-problems "description"

Documentation:
- Workflow: See `cca-core` skill
- Commands: See `cca-core`
- Search: Use `cca-searching` skill
- Health check: Run `cca-doctor`
```

## Example Server Configurations

### Ansible Project (.cca-env)
```bash
export TMUX_SESSION_SERVERS="server1 server2 server3"
export TMUX_SESSION_NAME=CCA_PROJECT
export ADMIN_NAME=username
```

### Standalone (servers.json)
```json
{
  "servers": [
    {"name": "server1", "host": "server1.example.com", "role": "web"},
    {"name": "server2", "host": "server2.example.com", "role": "db"}
  ]
}
```


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
