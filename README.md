# CCA - Cyber-CLI Admin

**Agent-agnostic server management, incident resolution, and knowledge management system.**

Universal toolkit usable by any AI agent that supports skills: `bin/` scripts for PATH and
`skills/` in `skill-name/SKILL.md` format. Every script supports `--help`; it is the reference,
this README is only the map.

## `cca` - unified CLI (in progress)

The `bin/` scripts are being replaced by one Python command, `cca <subcommand>`
(design: `backlog/docs/doc-1`, config schema: `backlog/docs/doc-2`). It reads settings
only from the project's `.cca.toml` and secrets only from the project's sops files.
`bin/`, `lib/` and `skills/` below stay unchanged until every project has migrated.

Install a release (Python 3.11+, [uv](https://docs.astral.sh/uv/)); non-editable, so work
in this clone never affects running agents:

```bash
uv tool install --reinstall "cca @ git+file:///path/to/cca-clone@vX.Y.Z"
cca --version
```

| Subcommand | Description |
|------------|-------------|
| `cca config show` | The `.cca.toml` in use and its values with defaults |
| `cca doctor [--fix]` | Check the project (config, sops, `cca/` dirs, skill links, old `cca-*` scripts/skills not installed) |
| `cca install skills [NAME] [--target DIR]` | Link the skills shipped in the package (`src/cca/skills/`) into `.claude/skills` |
| `cca open-ports [-d SERVER] [-k] [-m nmap\|nc\|curl] [-n] HOST [PORT...]` | Probe TCP ports of a host, locally or from a `[servers]` entry over ssh |

## bin/ - Scripts

| Script | Description |
|--------|-------------|
| `cca-install` | Symlink scripts and skills into place |
| `cca-doctor` | Check the project's CCA setup (`--fix` removes broken skill links) |
| `cca-tmux-cli` | Run commands in visible SSH sessions via tmux |
| `cca-run-on-server` | Run a command or create a file on a server (tmux-cli or ssh backend) |
| `cca-run-all` | Run a `cca-*` script against every configured server |
| `cca-server-hostname` / `cca-server-info` / `cca-server-status` | Basic server facts |
| `cca-diagnose-gather` | Gather diagnostics for troubleshooting |
| `cca-check-domain` | Domain health checks (DNS, our IPs, hosting marker) |
| `cca-watchlist` | Manage `watchlist.json` (agenda, ready, search, edits) |
| `cca-hetrix` | HetrixTools monitoring status |
| `asn-wrap` | ASN/IP lookup with compact `-s` output (unprefixed name kept on purpose; install by hand, `cca-install bin` links only `cca-*`) |
| `cca-curl-secret` | curl with credentials from a SOPS file |
| `cca-validate-args` | Reject shell metacharacters in arguments |
| `cca-check-shared-clean` | Check this repo against a project-supplied denylist |

## skills/ - Agent Skills

| Skill | Purpose |
|-------|---------|
| `cca-core` | Mandatory entry point before any server work |
| `cca-solving-problems` | Unified problem resolution, including security incidents |
| `cca-asking` | Natural-language server questions |
| `cca-diagnosing` | Context-aware troubleshooting |
| `cca-server-discovery` | Discover services on an unknown server |
| `cca-server-logs` | System and service log analysis |
| `cca-watching` | Daily watchlist check |
| `cca-managing-watchlist` | Edit the watchlist with `cca-watchlist` |
| `cca-creating-incidents` | Create or update incident records |
| `cca-saving-guides` | Save a solved issue as a guide |
| `cca-optimizing-guides` | Monthly knowledge-base maintenance |
| `cca-learning` | Integrate session learnings into the knowledge base |
| `cca-searching` | Full-text search of guides and incidents |
| `cca-researching-web` | Web research: docs, bugs, CVEs |
| `cca-hetrix-monitoring` | HetrixTools monitoring and outages |
| `cca-tmux-cli` | `cca-tmux-cli` usage |
| `cca-setting-up` | Initial CCA setup in a project |
| `cca-migrating` | Migrate CCA between repositories |
| `cca-creating-skills` | Create new CCA skills |

## Installation

Targets must already exist; links point back into this repo.

```bash
./bin/cca-install bin ~/bin      # scripts
./bin/cca-install skills         # all skills into ./.claude/skills of the current project
```

### Dependencies

- bash, Python 3.10+
- tmux (`cca-tmux-cli`)
- yq (mikefarah v4); sops (`cca-curl-secret`); jq (`cca-hetrix`); asn (`asn-wrap`)
- [tantivy2agents](https://github.com/orgoj/tantivy2agents) for search

## Project configuration

Scripts read project data from the current directory, never from their install location.
Config is searched from the CWD up to the git root (never `$HOME` or above), closest first:
`.cca-tmux-cli` > `.cca-env` > `.env` (legacy). Key variables: `ADMIN_NAME`,
`TMUX_SESSION_NAME`, `TMUX_SESSION_SERVERS`, `RUN_ON_CMD`, plus project-specific `CCA_*`.

```
project/
├── .cca-env               # Project config
├── cca/
│   ├── guides/            # Knowledge base (incl. guides/servers/<name>.md)
│   ├── incidents/         # Incident records
│   └── watchlist.json     # Monitoring tasks
├── logs/                  # Command logs (written when the directory exists)
├── .claude/skills/        # Symlinks to shared cca-* skills
└── .tantivy-data/         # Search index
```

## Tests

```bash
tests/run-all.sh                 # shellcheck, bash tests, ruff, pytest, build + install smoke
tests/test-shared-clean.sh       # run from a project directory that supplies the denylist
```

`run-all.sh` also fails when `bin/`, `lib/` or `skills/` differ from the `legacy-baseline`
tag, and scans `backlog/`, `src/` and the built wheel/sdist with the fixture denylist
`tests/fixtures/leak-denylist.txt`.

## Release

One subcommand (or a tightly coupled family) per release; tags are `v<version>` and are
never moved.

1. Bump `version` in `pyproject.toml`, commit.
2. Pre-tag check (needs the consumer project's denylist, fails without it):
   `CCA_DENYLIST=/path/to/denylist tests/release-check.sh pre-tag`
   (clean work tree, tag not yet present, `run-all.sh`, shared-clean and package checks
   with that denylist).
3. Tag: `git tag -a vX.Y.Z -m "cca X.Y.Z"`.
4. Post-tag check: `CCA_DENYLIST=/path/to/denylist tests/release-check.sh post-tag`
   (the tag equals the package version and points at HEAD).
5. Install: `uv tool install --reinstall "cca @ git+file:///path/to/cca-clone@vX.Y.Z"`,
   then `cca --version`.

## License

MIT
