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
source checkout must be fully usable (incl. skills) at every release.

## Settled decisions

- All functionality becomes `cca` subcommands; unified secrets, config, output, tests.
- **Configuration only from `.cca.toml`, exactly one per project, no merging.** CCA reads
  no configuration and no secret from `.cca-env`, `.env`, `.cca-tmux-cli` or environment
  variables (several projects with different keys share one machine).
- Secrets only from per-project sops files.
- `cca run` = improved Python successor of `cca-tmux-cli`, `cca-run-on-server` and
  `cca-run-all` (the bash scripts are the behavioral reference); transports tmux | ssh, chosen in
  `.cca.toml`. Validation of the agent's tool call `cca run SERVER ...` is done by Dippy
  with the agent CLI, outside CCA. Optional later: `cca run` asks the Dippy CLI to
  validate the inner command with server context.
- **Running agents must see no change until the new `cca` is finished and deployed.**
  `bin/`, `lib/` and the root `skills/` (symlinked live into consumer projects) stay
  byte-for-byte unchanged until TASK-2. New `cca` skills are written separately in
  `src/cca/skills/`, packaged into the wheel, and reach a project only when it migrates
  (old skill links removed, `cca install skills` run). Each new skill is added with the
  subcommand it uses.
- Windows skill installation is out of scope for now (deferred task); on platforms
  without symlink support `cca install skills` fails with a clear error.
- `cca-install` has no successor (uv installs `cca`; skills via `cca install skills`).
- `cca-validate-args` is not ported (no consumers; command validation is Dippy's job).
- `cca-check-shared-clean` stays bash, repo-only check.
- `tmux_cli_python/` (unused experiment: package, entry point, tests, YAML config, its
  hooks/audit features) is removed in phase 1; `cca run` does not inherit its
  hook/audit pipeline. It stays available in git history.
- Old `cca-*` scripts stay unchanged (no deprecation notes, no edits) until all
  consumer projects are converted to `cca`, then they are deleted (with
  `lib/cca-env.sh` and root `skills/`) in a separate, user-approved task.
  `tests/run-all.sh` enforces this: it fails when `bin/`, `lib/` or root `skills/`
  differ from the `legacy-baseline` tag. `cca-tmux-cli` may remain as a
  thin wrapper over `cca run`, depending on how agents adapt; the user decides later.
- Install: non-editable from a tag, so CCA work never breaks running agents.

## Config: `.cca.toml`

- Parsed with stdlib `tomllib` (requires-python >= 3.11).
- Discovery: walk the **physical** CWD path (`os.getcwd()`, no `PWD`) up to `/`
  (exclusive); the first `.cca.toml` is the config and the walk stops. A nearer
  `.cca.toml` (e.g. in a nested repo) shadows the project's; by convention there is
  only one.
- `--config PATH` disables discovery; CLI path arguments resolve from the invocation
  CWD; paths inside the TOML resolve from the TOML's directory.
- Malformed/unreadable nearest file → error (exit 2), never fall back to a parent.
  None found → commands needing config exit non-zero with a clear message; commands
  that need none (`--version`, `install skills`) still work; `doctor` reports the missing
  config as FAIL and still runs its install checks.
- `schema_version` (integer). A file with a higher version than the installed `cca`
  supports → error. Unknown keys → warning on stderr (newer config on an older release
  stays usable, typos stay visible).
- The normative schema (tables, keys, types, defaults, validation, per-command secret
  file shapes, mapping from every legacy variable/file) lives in doc-2 with schema
  fixtures; doc-2 is written before the core implementation.
- Legacy inputs doc-2 must map: `CCA_OUR_IPS`, `CCA_HOSTING_MARKER`,
  `CCA_APACHE_STATUS_CMD`, `CCA_MONGODB_STATUS_CMD`, `CCA_NET_IFACE_PREFIXES`,
  `CCA_LOGGING`, `ADMIN_NAME`, `CCA_AGENT`, `CCA_TMUX_TOKF`, `CCA_WATCHLIST`,
  `.cca-tmux-cli` settings (session, servers),
  `.netdata-servers`, cloudflare exports and fping cache paths, secrets paths. Not
  config: `CCA_DENYLIST` (bash repo check), `CCA_ENV_FILES`, `CCA_ROOT`, `CCA_SKILLS`.
- `[servers.<name>]` is the shared server registry (ssh target, netdata address, ...).
- `.cca.toml` may define commands CCA executes (e.g. status commands), so it is trusted
  project code, like a Makefile.
- `cca config show`: the config path plus the validated document; never decrypts secrets.

## Secrets: `cca.secrets`

- `sops -d --output-type json <file>`, invoked only by commands that need a secret;
  decrypted output never logged or echoed. File shapes per command in doc-2.
- Errors exit 2 naming what is missing (sops not on PATH, file missing, decrypt
  failure, key missing). No plaintext fallback.
- Secrets never in CCA-generated child argv, logs or diagnostics: headers wherever the
  API allows; tokens needed in the URL (`{TOKEN}` in `cca curl`) go through
  `curl --config -` on stdin.
- SDK clients get credentials and endpoints explicitly from the project's sops file and
  config; ambient SDK fallback (env tokens, default config files) is disabled; missing
  project secret → fail closed. Child processes otherwise inherit the environment
  (sops key providers, proxies) intentionally.

## `cca curl` request policy

- Each credential lists allowed origins: scheme + normalized host + effective port;
  HTTPS only; the request URL must match one allowed origin.
- URL checks cover every way curl accepts a URL: positional, `--url`, globbing/
  alternate forms, URLs from config files; any second URL is rejected.
- Ambient curl config is disabled (`-q` / no `.curlrc`); user `-K/--config`,
  `--write-out`, `-v`, `--trace*`, `--libcurl` and other options that bypass the policy
  or print request data are rejected when a credential is attached.
- No credential forwarding on redirects to another origin.
- Values written to the curl config are escaped; control characters rejected.
- Output: configured secret values are redacted from curl stdout, stderr and CCA error
  paths (covers endpoints that reflect the token-bearing URL or header).
- `secrets/curl.secret.yaml` keeps `credentials.<id>.*`; doc-2 adds the origin list.

## `cca run`

- Surfaces (all bash predecessors covered): run a command, `list`, `read`, `session`,
  `--create-file` (atomic remote write), `--list` (servers), `--all`. Surfaces
  meaningless for a transport (e.g. `read` over ssh) are rejected with a clear error.
- `cca-run-all` (ran a server-taking script once per server) is replaced by `--all`:
  `cca run --all -- CMD` runs CMD on every `[servers]` entry in config order, output
  tagged per server, stops on the first failure; server-taking subcommands
  (`server info/status/hostname`, `diagnose`) accept `--all` with the same semantics.
  No arbitrary script names.
- Execution is a reusable executor API (server, command, transport); `cca run` is a
  thin CLI over it and `server`/`diagnose` use it instead of their own ssh code.
- Shape: `cca run [options] SERVER -- CMD...` or `cca run [options] SERVER <<'EOF'`.
  No CMD → read the command from stdin: stdin is a TTY → error; empty stdin → error.
  Server is the first positional; value options only before it, from a known list.
  The shape is a public contract for external validators (Dippy).
- Security: no local shell is involved in building the call; SERVER only from
  `[servers]`, ssh target validated and passed as separate argv; tmux targets passed as
  separate argv. If output redaction is added later, it applies to every output path
  (normal, timeout, error, log) and empty redactor output stays empty.
- Reserved for later: `[run] validator = "dippy"`.

## Layout

Single Python project at repo root, so skills ship inside the wheel:

```
pyproject.toml            # project "cca"; scripts: cca = "cca.cli:main"
src/cca/cli.py            # argparse, lazy import per subcommand
src/cca/{config,secrets,output,ssh}.py
src/cca/commands/<name>.py
src/cca/skills/           # new cca skills, packaged into the wheel
skills/                   # old skills, unchanged until TASK-2 (live symlinks in projects)
tests/                    # bash tests stay; pytest for cca
```

- The wheel ships `src/cca/skills/` only; every skill there references only commands that
  exist in that release; a wheel-install test scans installed skills for references to
  commands not provided (incl. any old `cca-*` name).
- `cca install skills [NAME] [--target DIR]` (default `.claude/skills`, must exist)
  symlinks from the installed package (`importlib.resources`); replaces only links it
  owns (recorded in `DIR/.cca-skills.json`, or live links to the same skill of a cca
  install), never overwrites other skills or follows existing destination links;
  idempotent; links stay valid after reinstall.
- Phase 1 removes `tmux_cli_python/`, its tests and its dependencies (typer, pyyaml,
  libtmux) together with the root project switch.

## Subcommand inventory

| Subcommand | From |
|---|---|
| `--version`, `config show`, `doctor [--fix]` | new / `cca-doctor` |
| `install skills [NAME]` | `cca-install skills` (bin mode: no successor) |
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
| `run` | `cca-tmux-cli`, `cca-run-on-server`, `cca-run-all` |
| not ported | `cca-validate-args`, `cca-install bin`, `tmux_cli_python` (removed in phase 1) |
| stays bash | `cca-check-shared-clean` (repo check) |

Each port has a compatibility matrix (flags, defaults, output paths, exit codes,
intentional changes); every row tested; external tools checked lazily; texts English
with `server1`/`example.com`/`203.0.113.x`. The three tools from the private Ansible
project are first captured in public-safe behavior specs in `backlog/docs` (TASK-1.9),
so their ports and doc-2 can be done from a clone.

## Release check and install

- `tests/run-all.sh` (stays bash) adds pytest + ruff, `uv build`, wheel/sdist content
  check (skills present, no denylisted strings), install smoke into temporary
  `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` running `cca --version` and `cca install skills`.
- Leak check: automated tests use a repository fixture denylist; the release step
  requires the consumer denylist and fails closed if it is unavailable.
- Pre-tag check: version not yet tagged. Post-tag check: tag equals package version.
  Tags are never moved.
- Install: `uv tool install --reinstall "cca @ git+file://<clone>@vX.Y.Z"` (syntax
  verified in phase 1, recorded in README). Version from `importlib.metadata`.
- Two releases: the core + doctor link check (TASK-1.10, v0.1.0) and the complete `cca`
  with all ports and `cca run` (TASK-1.11); subcommands are not released one by one
  (user decision). A port task closes when `tests/run-all.sh` is green (fixture
  denylist); consumer-denylist check, tagging, post-tag check and install happen in
  TASK-1.11.

## Consumer migration

A one-time manual conversion (TASK-4), started only after the complete `cca` is
finished, reviewed and approved by the user: per consumer project write `.cca.toml`
from the doc-2 legacy input mapping, move secrets into sops files, replace old skill
links with `cca install skills`, switch scripts, docs, skills and agent instructions to
`cca <sub>`, remove legacy config files. `cca` itself never scans project content for
old usage.
`cca doctor` checks only the new state, including that no agent skill dir or PATH dir
is, or contains a link to, the old CCA `bin/` or root `skills/` (doc-2 "Old CCA links").
Old scripts and skills are removed (TASK-2) only when every consumer is converted and
`cca doctor` passes there.

## Phases

0. Public-safe behavior specs of the three Ansible-project tools (TASK-1.9), then
   doc-2: normative `.cca.toml` + secrets schema v1 with fixtures.
1. Core: skeleton, config + secrets modules, `config show`, `doctor`, `install skills`,
   release check, install smoke.
2. Ports, one task each: open-ports, netdata, cloudflare.
3. Ports, one task each: curl, hetrix, check-domain, server-*, asn, diagnose, watchlist.
4. `cca run`, then one release of the complete `cca` (TASK-1.11).
5. Global docs update and migration guide.
Later, separate: Windows skills install (deferred); removal of old scripts after all
consumers migrated (user approval).
