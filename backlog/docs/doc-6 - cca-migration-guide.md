---
id: doc-6
title: cca migration guide
type: guide
created_date: '2026-10-15 20:13'
---

# cca migration guide

How a consumer project moves from the old `cca-*` scripts, `lib/cca-env.sh` and the
root `skills/` of this repo to the `cca` command. The conversion is done once per
project, by hand (TASK-4), and starts only after the user approves the complete `cca`.
`cca` itself never scans project content for old usage. The old scripts and skills are
deleted (TASK-2) only when every consumer project is converted and its `cca doctor`
reports no old CCA link (step 8).

Schema of the new config: doc-2. Design and command behavior: doc-1 and
`cca <subcommand> --help`.

## Steps

1. **Install** a release: `uv tool install --reinstall "cca @ git+file://<clone>@vX.Y.Z"`,
   then `cca --version` (README "Install").
2. **Config**: write one `.cca.toml` in the project root with `schema_version = 1` and
   every input of the project mapped by "Legacy inputs" below. Server names keep the
   order of `TMUX_SESSION_SERVERS` (it is the `--all` order). Check with
   `cca config show`: no error, no `unknown key` warning.
3. **Secrets**: the curl file keeps its path and `credentials.<id>` entries; add the
   required `origins` list to every credential (doc-2 "`secrets.curl`": the credential
   is now selected by the request origin, not by an id derived from the hostname).
   Move the Cloudflare token into the sops file `secrets.cloudflare`, key `api_token`.
   No secret stays in an env file.
4. **Watchlist → Backlog.md** (doc-1 "Watchlist on Backlog.md"): without `backlog/`,
   `backlog init "<name>" --defaults --integration-mode none --default-editor ""` (no
   `AGENTS.md`/`CLAUDE.md` change); statuses `["Idea", "To Do", "In Progress", "Note",
   "Done"]`. Stop writing the legacy watchlist, then `cca watchlist migrate
   <path>/watchlist.json` (dry run): review every line and warning, move machine-only
   items to the agent bundle `TODO.md` and pass them as `--exclude ID`. Run it again with
   `--apply` and commit `backlog/`. Verify with a third dry run: every open,
   non-excluded item reports `exists`, none `new`. Finished items are not converted.
5. **Skills**: remove every link into the old CCA `skills/` from the project's agent
   skill dirs, then `cca install skills` (default `.claude/skills`; `--target DIR` for
   other agents). Old skills without a successor: see "Skills".
6. **Commands**: replace every old command in scripts, Makefiles, CI, docs, guides,
   incident templates, project skills, agent instructions and command validator rules
   using "Commands" below. Check that nothing is left:
   `grep -rn -E '\b(cca-(tmux-cli|run-on-server|run-all|server-(hostname|info|status)|diagnose-gather|check-domain|curl-secret|hetrix|watchlist|doctor|install|validate-args)|asn-wrap)\b' .`
   (exclude `.git` and vendored trees; hits in old incident records may stay as history).
7. **Remove legacy config**: `.cca-env`, `.cca-tmux-cli`, `.tmux-cli-python.yaml`,
   `.netdata-servers`, `watchlist.json`, and the mapped keys in `.env` (other `.env`
   keys belong to the project and stay).
8. **Check**: `cca doctor` in the project exits 0 and reports no old CCA script or
   skill, neither FAIL (project skill dirs) nor WARN (user-level skill dirs and `PATH`
   dirs, e.g. `~/bin` links into the old `bin/`). The user-level links are shared by
   all projects, so they are removed after the last project is converted; then
   `cca doctor` must report no old link in every consumer project. **This is required
   before TASK-2.**

## Legacy inputs

Every input listed in doc-1 "Legacy inputs the mapping must cover", plus inputs found in the
legacy sources. Step 2 replaces each name in the left column.

| Legacy input | Read by | v1 |
|---|---|---|
| `CCA_OUR_IPS` (comma list) | `cca-check-domain` | `check_domain.our_ips` (split on `,`, trimmed) |
| `CCA_HOSTING_MARKER` | `cca-check-domain` | `check_domain.hosting_marker` |
| `CCA_APACHE_STATUS_CMD` | `cca-diagnose-gather` | dropped: `cca-diagnose-gather` is not ported (doc-1 inventory) |
| `CCA_MONGODB_STATUS_CMD` | `cca-diagnose-gather` | dropped: `cca-diagnose-gather` is not ported (doc-1 inventory) |
| `CCA_NET_IFACE_PREFIXES` (`a\|b` regex) | `cca-server-info` | `server_info.net_iface_prefixes` (split on `\|`) |
| `CCA_LOGGING` | shown by `cca-tmux-cli --doctor` only | dropped: never controlled logging; presence of `[run.log]` does |
| log dir `logs/` (hard-coded, logging when it exists) | `cca-tmux-cli`, `cca-run-on-server` | `run.log.dir`; **intentional change**: logging is explicit, not triggered by the directory |
| `ADMIN_NAME` | `cca-tmux-cli`, `cca-run-on-server`, `cca-doctor` | `run.log.operator`, optional: omit it in a shared repo, the OS login name of each admin is used |
| `CCA_AGENT` | `tmux_cli_python` audit | dropped with `tmux_cli_python` (phase 1) |
| `CCA_TMUX_TOKF=1` | `cca-tmux-cli` | `run.tokf = true` |
| `CCA_WATCHLIST`, `watchlist.json` | `cca-watchlist` | dropped: the register is the project's Backlog.md (step 4) |
| `TMUX_SESSION_NAME` (`.cca-tmux-cli`/`.cca-env`) | `cca-tmux-cli` | `run.tmux.session` |
| `TMUX_SESSION_SERVERS` (space list) | `cca-tmux-cli`, `cca-run-on-server`, `cca-doctor` | one `[servers.<name>]` table per entry, same order |
| `RUN_ON_CMD` (`cca-tmux-cli`\|`ssh`) | `cca-run-on-server` | `run.transport` (`"tmux"`\|`"ssh"`) |
| `.cca-tmux-cli`, `.cca-env`, `.env` files | `lib/cca-env.sh`, `cca-tmux-cli` | dropped as config sources; their keys map by the rows above |
| `.tmux-cli-python.yaml` | `tmux_cli_python` | dropped with `tmux_cli_python` |
| `.netdata-servers` `NAME HOST[:PORT] [SSH_HOST]` | `netdata-cli` (doc-4) | `[servers.NAME]`: `netdata_host`, `netdata_port` (default 19999), `ssh = SSH_HOST`; no third column → `netdata_transport = "direct"` |
| fping cache `server-logs/fping/` (CWD-relative) | `netdata-cli fping --history` | `netdata.fping_cache_dir` (config dir relative) |
| consumer-specific default `--target` | `netdata-cli fping` | `netdata.fping_target` |
| cloudflare export dir `tmp/cloudflare/` (script-relative root) | `cloudflare-cli` (doc-5) | `cloudflare.export_dir` (config dir relative) |
| `CLOUDFLARE_API_TOKEN` (env, `.cca-env[.local]`, `.env[.local]`) | `cloudflare-cli` | sops `cloudflare` file, key `api_token` |
| Cloudflare SDK ambient configuration (env base URL and other SDK defaults) | `cloudflare` SDK in `cloudflare-cli` | dropped; the endpoint is pinned (`cloudflare.api_base` accepts only `https://api.cloudflare.com/client/v4`), all ambient SDK fallbacks disabled |
| `secrets/curl.secret.yaml` (CWD-relative) | `cca-curl-secret`, `cca-hetrix` | `secrets.curl` (config dir relative) |
| `HETRIX_API_KEY` (comment only, never read) | – | dropped; hetrix uses a `curl` credential |

Not config (doc-1): `CCA_DENYLIST` (bash repo check), `CCA_ENV_FILES`, `CCA_ROOT`,
`CCA_SKILLS`.

## Commands

Options not listed keep their meaning; `--help` of the new command is authoritative.

| Old | New |
|---|---|
| `cca-tmux-cli -t S run "CMD"` | `cca run -t S -- CMD` |
| `cca-tmux-cli -t S run --script <<'EOF'` | `cca run -t S <<'EOF'` |
| `cca-tmux-cli -t S read` | `cca run --read S` (`--lines N`, `--marker M`, `--scrollback`) |
| `cca-tmux-cli list` | `cca run --list` |
| `cca-tmux-cli session S...` | `cca run --session [S...]` |
| `cca-tmux-cli -s SESSION`, `--interval`, `-x` | dropped: the session is `run.tmux.session`; no poll interval or debug option |
| `cca-tmux-cli --robot-init`, `--doctor`, `--robot-help` | `cca doctor`, `cca run --help`, skill `cca` |
| `cca-run-on-server S "CMD"` | `cca run -t S -- CMD` (transport from `run.transport`) |
| `cca-run-on-server S --create-file PATH [LOCAL]` | `cca run --create-file PATH S` with the content on stdin (`< LOCAL`) |
| `cca-run-on-server --list` | `cca run --list` |
| `cca-run-all SCRIPT` | `cca run --all -- CMD`, `cca server hostname\|status\|info --all` |
| `cca-server-hostname`, `cca-server-status`, `cca-server-info` `S` | `cca server hostname\|status\|info S` |
| `cca-diagnose-gather` | not ported: `cca server status` and `cca run` |
| `cca-check-domain D` | `cca check-domain D` |
| `cca-curl-secret [--cred-id ID] ... URL` | `cca curl [--cred-id ID] ... URL` (HTTPS only, credential by origin, `-L` rejected) |
| `cca-hetrix --up`, `--down`, `--all`, `--response-times` | `cca hetrix status`, `down`, `all`, `response-times` |
| `cca-hetrix --outages [--since T] [--until T]` | `cca hetrix outages [--since T] [--until T]` |
| `cca-hetrix --monitor-outages M`, `--monitor-info M`, `--server-stats M` | `cca hetrix monitor-outages M`, `monitor-info M`, `server-stats M` |
| `cca-hetrix --blacklist`, `--blacklist-ip IP` | `cca hetrix blacklist`, `cca hetrix blacklist IP` |
| `asn-wrap -s IP...`, `asn-wrap IP...` | `cca asn IP...`, `cca asn --json IP...` (no reputation field; the registry range `net_range` is `net:` / `registry.cidrs`) |
| `cca-watchlist list-today`, `agenda` | `cca watchlist today` (Due, Priority) |
| `cca-watchlist update ID` | `cca watchlist checked ID` |
| `cca-watchlist ready`, `next` | `cca watchlist ready`, `cca watchlist next` (same options) |
| `cca-watchlist list --current`, `--expired` | `cca watchlist notes`, `cca watchlist notes --expired` |
| `cca-watchlist migrate` (v1 → v2) | not ported; convert a v1 file with it before `cca watchlist migrate` |
| other `cca-watchlist` subcommands | the `backlog` CLI (`task list`, `task view`, `search`, `task create`, `task edit --plan`, `task archive`) with the doc-1 labels |
| `cca-doctor [--fix]` | `cca doctor [--fix]` |
| `cca-install skills` | `cca install skills` |
| `cca-install bin DIR` | `uv tool install` (step 1) |
| `cca-validate-args` | not ported (command validation is the validator's job) |
| `cca-check-shared-clean` | stays in this repo (repo check only) |
| `check-open-ports`, `netdata-cli`, `cloudflare-cli` of the Ansible project | `cca open-ports`, `cca netdata`, `cca cloudflare` |

## Skills

The package ships one skill, `cca` (`cca install skills`), with a reference file per
subcommand.

User decision: the packaged `cca` skill alone replaces every old skill; all old `cca-*`
skill links are removed from every project (`cca doctor` flags them). Project specifics
stay in the project's guides, not in project copies of old skills.

| Old skill | Successor in skill `cca` |
|---|---|
| `cca-core` | `SKILL.md` rules, `references/knowledge.md`, `references/operations.md` |
| `cca-tmux-cli` | `references/run.md`, `references/operations.md` "Safety" |
| `cca-solving-problems`, `cca-diagnosing`, `cca-server-discovery`, `cca-server-logs` | `references/operations.md` (the `cca-diagnose-gather` part is dropped, not ported) |
| `cca-hetrix-monitoring` | `references/hetrix.md` "Outage investigation" |
| `cca-searching` | `references/knowledge.md` |
| `cca-creating-incidents`, `cca-saving-guides`, `cca-learning` | `references/records.md` |
| `cca-optimizing-guides` | `references/maintenance.md` (watchlist cleanup → register cleanup on Backlog.md) |
| `cca-watching`, `cca-managing-watchlist` | `references/watchlist.md` |
| `cca-setting-up` | `references/config.md`, `doctor.md`, `install.md`, `watchlist.md` "Setup", `knowledge.md` (index) |
| `cca-asking`, `cca-researching-web`, `cca-creating-skills`, `cca-migrating` | dropped: agents answer natively, web research goes to the research agent, skills are created with the machine's skill tooling, migration is this guide |
