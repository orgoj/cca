# CCA - Claude Code Admin

**Agent-agnostic server management, incident resolution, and knowledge management system.**

Universal toolkit usable by any AI agent that supports skills. Includes shell scripts (add to PATH) and skills (copy to your agent's skill directory).

## Components

### bin/ - Shell Scripts

Add to PATH for universal access:

```bash
export PATH="$PATH:/path/to/cca/bin"
```

| Script | Description |
|--------|-------------|
| `cca-doctor` | Check CCA environment and configuration |
| `cca-tmux-cli` | Tmux session management with agent-friendly commands |
| `cca-run-on-server` | Execute commands on remote servers |
| `cca-watchlist` | Manage monitoring watchlist |
| `cca-diagnose-gather` | Gather system diagnostics |
| `cca-check-domain` | Domain health checks |
| `cca-learn-analyzer` | Analyze sessions for learnings |
| `cca-run-all` | Run command on all servers |
| `cca-server-hostname` | Get server hostname |
| `cca-server-info` | Get server information |
| `cca-server-status` | Check server status |
| `cca-session-setup` | Setup session environment |
| `cca-validate-args` | Validate command arguments |
| `cca-install` | Installation helper for binaries and skills |

### skills/ - Agent Skills

Copy to your agent's skill directory. Each skill is a directory with `SKILL.md`.

| Skill | Description |
|-------|-------------|
| `cca-problem` | Main entry point - unified problem resolution workflow |
| `cca-ask` | Natural language interface for server queries |
| `cca-diagnose` | Context-aware troubleshooting |
| `cca-watch` | Daily watchlist monitoring |
| `cca-incident-create` | Create incident documentation |
| `cca-guide-save` | Save resolved issues as guides |
| `cca-guide-optimize` | Monthly knowledge base maintenance |
| `cca-learn` | Extract learnings from sessions |
| `cca-analyze-log` | Suggest new auto-approval patterns |
| `cca-setup` | Initial CCA system setup |
| `cca-search` | Full-text search for guides/incidents |
| `cca-migration` | Migrate CCA between repositories |
| `cca-web-researcher` | Web research for docs, CVEs, bugs |
| `cca-watch-manager` | Watchlist management agent |

### tests/ - Test Scripts

```bash
tests/test-command-safety.sh     # Test base64 command escaping
tests/test-signal-handling.sh    # Test cca-tmux-cli signal handling
```

## Installation

### Quick Install (recommended)

1. **Install binaries to ~/bin:**
   ```bash
   ./bin/cca-install bin ~/bin
   ```

2. **Install skills locally:**
   ```bash
   ./bin/cca-install skills
   ```

### Manual Installation

**Add bin to PATH:**
   ```bash
   export PATH="$PATH:/path/to/cca/bin"
   ```

**Copy skills to agent's skill directory:**
   ```bash
   cp -r skills/* /path/to/agent/skills/
   ```

### Dependencies

- Python 3.8+
- jq
- tmux (for cca-tmux)
- [tantivy2agents](https://github.com/orgoj/tantivy2agents) for search

## Usage

### Problem Resolution Workflow

```
Problem occurs → cca-problem skill
├─ Guide found? → Follow guide → Done!
├─ Similar incident? → Auto-resolve (if safe)
└─ Unknown → Diagnostics → Manual fix
    └─ After fix: cca-incident-create + cca-guide-save
```

### Daily Monitoring

```
Morning check → cca-watch skill
├─ Query watchlist
├─ Check each item
└─ Update timestamps
```

### Natural Language Queries

Use `cca-ask` skill for questions like:
- "is MongoDB healthy?"
- "which server has most free space?"
- "can I safely restart server1?"

## Project Structure (after setup)

```
project/
├── servers.json           # Server configuration
├── watchlist.json         # Monitoring tasks
├── guides/                # Knowledge base
├── incidents/             # Incident documentation
├── logs/                  # Session logs
├── .claude/
│   ├── config/
│   │   └── ai-config.yaml # Safety rules
│   ├── danger/            # Auto-approval patterns
│   └── skills/
│       └── server-*/      # Server-specific skills
└── .tantivy-data/         # Search index
```

## License

MIT
