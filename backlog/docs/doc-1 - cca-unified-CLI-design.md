---
id: doc-1
title: cca unified CLI design
type: specification
created_date: '2026-10-15 07:12'
---

# Unified `cca` Python CLI (uv), config in `.cca.toml`

## Goal

The repo becomes a generic, easily installable server-administration toolkit usable in
any project, Ansible or not: **one command `cca <subcommand>`**, Python, installed with
`uv tool install` (non-editable, from a release tag). A plain uv install without a
source checkout must be fully usable (incl. skills).

## Settled decisions

- All functionality becomes `cca` subcommands; unified secrets, config, output, tests.
- **Configuration only from `.cca.toml`, exactly one per project, no merging.** No
  `.cca-env`, `.env`, `.cca-tmux-cli`, and **no environment variables** (several
  projects with different keys share one machine).
- Secrets only from per-project sops files.
- `cca run` = improved Python successor of `cca-tmux-cli` (built from `tmux_cli_python/`);
  transports tmux | ssh, chosen in `.cca.toml`. Validation of the agent's tool call
  `cca run SERVER ...` is done by Dippy with the agent CLI, outside CCA. Optional later:
  `cca run` asks the Dippy CLI to validate the inner command with server context.
- Skills are packaged into the wheel; `cca install skills` works from the installed tool.
- Dev tools: `cca-check-shared-clean` stays bash, repo-only gate; `cca-validate-args`
  becomes an internal module; `cca-run-all` becomes `cca run --all`.
- `tmux-cli-python` as a separate command is dropped; it becomes `cca run`.
- Old `cca-*` scripts stay unchanged until all consumer projects are converted, then
  deleted (with `lib/cca-env.sh`). `cca-tmux-cli` stays until agents move to `cca run`.
- Install: non-editable from a tag, so CCA work never breaks running agents.

## Config: `.cca.toml`

- Parsed with stdlib `tomllib` (requires-python >= 3.11).
- Discovery: walk from CWD up to `/` (exclusive); the first `.cca.toml` is the config and
  the walk stops. A nearer `.cca.toml` (e.g. in a nested repo) shadows the project's;
  by convention there is only one. Symlinked dirs: walk the logical CWD path.
- `--config PATH` disables discovery; CLI path arguments resolve from the invocation
  CWD; paths inside the TOML resolve from the TOML's directory.
- Malformed/unreadable nearest file → error (exit 2), never fall back to a parent.
  None found → commands needing config exit non-zero with a clear message; commands
  that need none (`--version`, `doctor` install checks, `install skills`) still work.
- Typed schema with top-level `schema_version = 1`, defined completely in phase 1 by
  inventorying every configurable value of all ported tools (`CCA_OUR_IPS`,
  `CCA_HOSTING_MARKER`, `CCA_APACHE_STATUS_CMD`, `CCA_MONGODB_STATUS_CMD`,
  `CCA_NET_IFACE_PREFIXES`, logging/admin/tokf settings, watchlist paths, run
  server/session/transport, output/cache paths, secrets paths). Unknown keys → error.
- `[servers.<name>]` is the shared server registry (ssh target, netdata address, ...),
  replacing ad-hoc files like `.netdata-servers`.
- `cca config show`: the config path plus the validated document; never decrypts secrets.

```toml
schema_version = 1

[servers.server1]
ssh = "root@server1.example.com"
netdata = "203.0.113.10:19999"

[run]
transport = "tmux"   # tmux | ssh
session = "admin"

[cloudflare]
secrets = "secrets/cloudflare.secret.yaml"
```

## Secrets: `cca.secrets`

- `sops -d --output-type json <file>`, invoked only by commands that need a secret;
  decrypted output never logged or echoed.
- Paths from `.cca.toml` (per subcommand). Errors exit 2 naming what is missing (sops not
  on PATH, file missing, decrypt failure, key missing). No plaintext fallback.
- Secrets never in child argv: headers wherever the API allows; APIs needing the token in
  the URL (`{TOKEN}` placeholder in `cca curl`) get the substituted URL through
  `curl --config -` on stdin, not argv.
- Tests assert the secret appears in no child argv, diagnostics, exception text,
  or captured stdout/stderr.
- "No environment" means CCA reads no config/secrets from env. Child processes
  (sops, ssh, curl, SDK) inherit the process environment as usual (sops key access,
  proxies); this is intentional.
- `secrets/curl.secret.yaml` schema (`credentials.<id>.*`, id from URL hostname) kept.

## Layout

Single Python project at repo root, so skills ship inside the wheel:

```
pyproject.toml            # project "cca"; scripts: cca = "cca.cli:main"
src/cca/cli.py            # argparse, lazy import per subcommand
src/cca/{config,secrets,output,ssh}.py
src/cca/commands/<name>.py
skills/                   # unchanged location; packaged into the wheel as cca/skills
tests/                    # bash tests stay; pytest for cca
```

- hatchling `force-include` maps `skills/` → `cca/skills`. Old `cca-install` keeps
  symlinking repo `skills/`.
- `cca install skills [TARGET]` symlinks from the installed package
  (`importlib.resources`), re-links idempotently after reinstall; copy fallback where
  symlinks are unavailable (Windows).
- The current root `pyproject.toml` (`tmux-cli-python`) is replaced by the `cca` project;
  `tmux_cli_python/` code moves into `cca.commands.run`.

## Subcommand inventory

| Subcommand | From |
|---|---|
| `--version`, `config show`, `doctor` | new / `cca-doctor` |
| `open-ports` | Ansible project `check-open-ports` |
| `netdata` | Ansible project `netdata-cli.py` |
| `cloudflare` | Ansible project `cloudflare-cli` |
| `curl` | `cca-curl-secret` |
| `hetrix` | `cca-hetrix` |
| `check-domain` | `cca-check-domain` |
| `server info/status/hostname` | `cca-server-*` |
| `asn` | `asn-wrap` |
| `diagnose` | `cca-diagnose-gather` |
| `watchlist` | `cca-watchlist` |
| `run` (+ `--all`) | `cca-tmux-cli`, `cca-run-on-server`, `cca-run-all`, `tmux_cli_python` |
| `install skills` | `cca-install skills` |
| internal module | `cca-validate-args` |
| stays bash | `cca-check-shared-clean` (repo gate) |

Each port: compatibility matrix first (flags, defaults, output paths, exit codes,
intentional changes), each row tested; external tools checked lazily, only when used;
Windows limits documented; source texts sanitized (English, `server1`/`example.com`/
`203.0.113.x`) and checked with `tests/test-shared-clean.sh` against the consumer
denylist before each release.

## `cca run` shape

- `cca run [options] SERVER -- CMD...` and `cca run [options] SERVER <<'EOF' ... EOF`.
- Server is the first positional after `run`; value options only before it, from a known
  list; command either after `--` or as a quoted heredoc on stdin; both or neither → error.
- The shape is a public contract for external validators (Dippy); changes need notice.
- Reserved for later: `[run] validator = "dippy"` to validate the inner command via the
  Dippy CLI before executing.

## Release gate and install

- `tests/run-all.sh` (stays bash) adds pytest + ruff for `cca`, `uv build`, wheel-content
  check (skills present), install smoke into temporary `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`
  running `cca --version` and `cca install skills` into a temp dir.
- Release: gate green → bump version → commit → tag `vX.Y.Z` (never moved, equals package
  version, checked by gate) →
  `uv tool install --reinstall "cca @ git+file://<clone>@vX.Y.Z"` (syntax verified in
  phase 1, recorded in README). Version from `importlib.metadata`.
- One subcommand (or one tightly coupled family) per release, after its matrix is green,
  so consumers migrate and roll back independently.

## Consumer migration

Per consumer project (by its owning agent, after the relevant release): write
`.cca.toml`, move secrets into sops files, switch calls/guides to `cca <sub>`.

## Phases

1. Core: project skeleton, config schema v1 + discovery tests, secrets module,
   `config show`, `doctor`, `install skills`, release gate, install smoke.
2. Ports, one release each: open-ports, netdata, cloudflare.
3. Ports, one release each: curl, hetrix, check-domain, server-*, asn, diagnose, watchlist.
4. `cca run` (+ `--all`).
5. Docs/skills update to `cca <sub>`, deprecation notes for old scripts.
