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
| `cca asn [--json] IP...` | One line per IP: ASN, country, type flags, RPKI, organization, PTR, registered range `net:` (RIPEstat, RIR RDAP, ipapi.is with the optional `curl` sops credential for its origin, DNS); non-global addresses are not looked up |
| `cca check-domain DOMAIN` | Does a domain point to our hosting: A/AAAA/CNAME, RDAP owner of foreign addresses, the `[check_domain]` hosting marker (same-host redirects only), redirect chain |
| `cca checkouts PATH PATH...` | Compare local checkouts of one repository, read-only (no fetch, merge or push): branch, HEAD, uncommitted changes, commits each lacks; exit 0 only on an identical HEAD and clean trees |
| `cca clean [--days N] [--apply]` | Delete top-level entries of the project's `tmp/` older than N days (default 30; a directory by its newest file), plan by default; `[clean] keep` and `cloudflare.export_dir` are kept, links never followed |
| `cca cloudflare GROUP COMMAND` | Cloudflare zones through the official SDK (token from sops): `token`, `zone`, `dns`, `waf`, `ratelimit`, `config`, `access`, `ua`, `uam`, `bots`, `events`, `analytics`, `export`, `diff`; writes plan unless `--apply` |
| `cca config show` | The `.cca.toml` in use and its values with defaults |
| `cca curl [--cred-id ID] [CURL-OPTION...] URL` | curl with a credential from the sops file, selected by the URL's origin (HTTPS only); kept out of argv and redacted from output and trace files |
| `cca doctor [--fix]` | Check the project (config, sops and the age key it will find, `cca run` needs when servers are configured: transport, ssh, tmux, session, `cca/` dirs, `backlog` CLI and its `Note`/`Done` statuses, skill links, old `cca-*` scripts/skills not installed) |
| `cca hetrix COMMAND` | HetrixTools API v3 with the `curl` sops credential for its origin: `status`, `down`, `all`, `response-times`, `outages`, `monitor-outages`, `monitor-info`, `server-stats`, `blacklist [TARGET]` |
| `cca install skills [NAME] [--target DIR]` | Link the skills shipped in the package (`src/cca/skills/`) into `.claude/skills` |
| `cca ioc status\|show\|baseline` | Read the host-ioc compromise check (deployed by the project role) from `[ioc] hosts`: last quick/deep run, age, version and `script_sha256` vs `ioc.script`, uncovered modules, findings; `show HOST [ID]` with read-only raw data; `baseline HOST` saves the proposal to `ioc.baseline_dir`; never writes on a host |
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
aliases = ["web"]                 # optional other names; resolve to server1 everywhere

[servers.server2]

[run]
transport = "tmux"                # or "ssh"

[run.tmux]
session = "example"

[run.log]                         # optional command log
dir = "logs"
# operator = "admin1"             # default: the OS login name of each admin
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

`run-all.sh` also scans `backlog/`, `src/` and the built wheel/sdist with the fixture
denylist `tests/fixtures/leak-denylist.txt`.

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
inputs → `.cca.toml` keys, old commands → `cca` subcommands, every old skill replaced by
the packaged skill `cca` (doc-6 "Skills": its references cover the knowledge workflow,
problem solving, discovery, logs and maintenance), removal of the legacy config files,
and `cca doctor` without old CCA links. Every project is converted; the old `cca-*`
scripts, their config loader and the old skills are removed (last state: tag
`legacy-baseline`). doc-6 maps each old command to its `cca` successor.

## License

MIT
