# CCA - Cyber-CLI Admin

**Agent-agnostic server management, incident resolution, and knowledge management system.**

One command, `cca <subcommand>`, for any project and any AI agent that supports skills.
It reads settings only from the project's `.cca.toml` and secrets only from the
project's sops files, never from environment variables. `cca --help` and
`cca <subcommand> --help` are the reference; this README is only the map.
Design: `backlog/docs/doc-1`, config schema: `backlog/docs/doc-2`, migration from the
old scripts: `backlog/docs/doc-6`.

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/). Install a release tag, non-editable,
so work in a clone never affects running agents:

```bash
uv tool install --reinstall "cca @ git+file:///path/to/cca-clone@vX.Y.Z"
cca --version
```

Then, in a project:

```bash
cca install skills     # link the shipped skill `cca` into .claude/skills (must exist)
cca doctor             # check config, sops, servers, transport, tools, skill links
```

External tools are looked up only by the subcommand that needs them: `ssh` (`run`,
`server`, `netdata`, `open-ports -d`), `tmux` (`run` with the tmux transport), `sops`
(secrets), `curl` (`curl`), `nmap`/`nc` (`open-ports`), `backlog`
([Backlog.md](https://github.com/MrLesk/Backlog.md) 1.53.0 or later, the tested version;
`watchlist`, `doctor`), `tokf` (optional,
`run.tokf`).

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `cca asn [--json] IP...` | One line per IP: ASN, country, type flags, RPKI, organization, PTR (RIPEstat, ipapi.is with the optional `curl` sops credential for its origin, DNS); non-global addresses are not looked up |
| `cca check-domain DOMAIN` | Does a domain point to our hosting: A/AAAA/CNAME, RDAP owner of foreign addresses, the `[check_domain]` hosting marker (same-host redirects only), redirect chain |
| `cca cloudflare GROUP COMMAND` | Cloudflare zones through the official SDK (token from sops): `token`, `zone`, `dns`, `waf`, `ratelimit`, `config`, `access`, `ua`, `uam`, `bots`, `events`, `analytics`, `export`, `diff`; writes plan unless `--apply` |
| `cca config show` | The `.cca.toml` in use and its values with defaults |
| `cca curl [--cred-id ID] [CURL-OPTION...] URL` | curl with a credential from the sops file, selected by the URL's origin (HTTPS only); kept out of argv and redacted from output and trace files |
| `cca doctor [--fix]` | Check the project (config, sops, `cca run` needs: servers, transport, ssh, tmux, session, `cca/` dirs, `backlog` CLI and its `Note`/`Done` statuses, skill links, old `cca-*` scripts/skills not installed) |
| `cca hetrix COMMAND` | HetrixTools API v3 with the `curl` sops credential for its origin: `status`, `down`, `all`, `response-times`, `outages`, `monitor-outages`, `monitor-info`, `server-stats`, `blacklist [TARGET]` |
| `cca install skills [NAME] [--target DIR]` | Link the skills shipped in the package (`src/cca/skills/`) into `.claude/skills` |
| `cca netdata [--server NAME\|--host H] COMMAND` | Netdata API of a server over ssh or directly: `list`, `meta`, `discover`, `stats`, `top`, `query`, `fping [--per-target\|--history\|--all]` |
| `cca open-ports [-d SERVER] [-k] [-m nmap\|nc\|curl] [-n] HOST [PORT...]` | Probe TCP ports of a host, locally or from a `[servers]` entry over ssh |
| `cca run [--timeout SEC] -t SERVER [-- CMD...]` | Run a command (or a stdin script) on a `[servers]` entry over tmux (visible window per server) or ssh; `--all`, `--create-file PATH`, `--list`, `--read`, `--session`; optional `[run.log]` command log and `tokf` |
| `cca server hostname\|status\|info` | Hostname, quick status (time, load, memory, ext/xfs, ZFS) or inventory (OS, CPU, disks, ZFS, interfaces, loopback aliases, Docker/Swarm/LXC/QEMU) of a `[servers]` entry or `--all`, always over ssh, one tag per section |
| `cca watchlist today\|notes\|checked\|ready\|next\|migrate` | Daily check over the project's Backlog.md (`backlog` CLI): due and `every:Nd` recurring tasks, high-priority actionable work, notes (status `Note`, `from:`/`until:` labels) valid on a date or expired, `checked ID` moves the next check; `ready`/`next` select work by `effort:`/`window:`/`change-risk:` labels; `migrate FILE` converts a legacy `watchlist.json` once |

## Project configuration

`cca` uses the first `.cca.toml` found from the current directory upwards (or
`--config PATH`); exactly one per project, no merging. Paths inside it resolve from its
directory. Every key, default and rule: `backlog/docs/doc-2`.

```toml
schema_version = 1

[servers.server1]                 # --all and listings use this order
ssh = "admin@server1.example.com" # default: the server name

[servers.server2]

[run]
transport = "tmux"                # or "ssh"

[run.tmux]
session = "example"

[run.log]                         # optional command log
dir = "logs"
operator = "admin1"
```

```
project/
├── .cca.toml              # Project config
├── secrets/               # sops files: curl.secret.yaml, cloudflare.secret.yaml
├── cca/
│   ├── guides/            # Knowledge base (incl. guides/servers/<name>.md)
│   └── incidents/         # Incident records
├── backlog/               # Backlog.md: tasks, recurring checks, notes (cca watchlist)
├── logs/                  # Command log ([run.log])
└── .claude/skills/        # Links made by `cca install skills`
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

Subcommands are not released one by one. Tags are `v<version>` and are never moved.

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

## Migration from the old scripts

Each project is converted once by hand following `backlog/docs/doc-6`: legacy config
inputs → `.cca.toml` keys, old commands → `cca` subcommands, old skills, removal of the
legacy config files, and `cca doctor` without old CCA links. The old scripts and skills
below are deleted only after every project is converted.

## Legacy: `bin/`, `lib/`, `skills/`

Still linked into projects that are not converted yet, so they stay byte-for-byte
unchanged until they are removed. Their configuration is read by `lib/cca-env.sh` from
the CWD up to the git root, closest first: `.cca-tmux-cli` > `.cca-env` > `.env`.

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
| `asn-wrap` | ASN/IP lookup with compact `-s` output |
| `cca-curl-secret` | curl with credentials from a SOPS file |
| `cca-validate-args` | Reject shell metacharacters in arguments |
| `cca-check-shared-clean` | Check this repo against a project-supplied denylist (stays) |

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

Install (targets must already exist; links point back into this repo):
`./bin/cca-install bin ~/bin`, `./bin/cca-install skills`. Dependencies: bash, Python
3.10+, tmux, yq (mikefarah v4), sops, jq, asn,
[tantivy2agents](https://github.com/orgoj/tantivy2agents) for search.

## License

MIT
