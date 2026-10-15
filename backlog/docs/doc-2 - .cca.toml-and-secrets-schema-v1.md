---
id: doc-2
title: .cca.toml and secrets schema v1
type: specification
created_date: '2026-10-15 09:23'
---

# `.cca.toml` and secrets schema v1

Normative contract for the `cca` core (TASK-1.1) and every port. Discovery, precedence and
the general rules (no environment variables, no merging, trusted project code) are in
doc-1 "Config" and "Secrets"; this document fixes the shape. A change to anything here
is a schema change: it bumps `schema_version` or is an additive optional key, never a
silent reinterpretation. Fixtures: `tests/fixtures/cca-toml/` and
`tests/fixtures/sops-shapes/` (see "Fixtures").

## General rules

- File: `.cca.toml`, parsed with `tomllib`. A syntax error, unreadable file or validation
  error exits 2 with the file path and the dotted key (`servers.server1.netdata_port`).
- **Config dir**: the directory containing the loaded `.cca.toml`. Every path value
  inside the file resolves from the config dir; absolute paths are allowed; a value
  starting with `~` is an error (no home expansion). CLI path arguments resolve from the
  invocation CWD (doc-1).
- Types are TOML types. An integer key rejects booleans and floats. A "name" is
  `^[A-Za-z0-9][A-Za-z0-9_-]*$`, at most 64 characters. Strings must be non-empty unless
  stated; strings that end up in a command or a file must not contain control characters
  (U+0000–U+001F, U+007F).
- Unknown keys and unknown tables: one warning per key on stderr
  (`cca: warning: unknown key 'run.validator' in /path/.cca.toml`), then ignored. This
  includes keys reserved for later (`run.validator`).
- **Load-time validation** (every command that loads config): `schema_version`, types,
  patterns and value ranges of every present key. **Use-time validation** (only the
  command that needs it): required-for-command keys, for example `run.tmux.session`
  for the tmux transport. A use-time error also exits 2 and names the key.
- `cca config show` prints the config path and the validated document with defaults
  filled in; it never opens a secrets file.

### HTTPS URLs

Applies to `cloudflare.api_base`, curl `origins` and every `cca curl` request URL, so
configured and requested origins compare by the same rules:

- Scheme `https` (case-insensitive) only. No userinfo (`@` before the host), no
  backslash, no whitespace or control characters anywhere.
- Host non-empty: an IP literal (IPv4, or IPv6 in `[…]`) or an ASCII DNS name (IDNA
  already applied). For a DNS name, at most one terminal `.` is removed first; the rest
  is 1–253 characters of labels separated by `.`, each label 1–63 characters matching
  `^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$` (no leading or trailing hyphen, no empty
  label).
- Port, when present, decimal digits only, 1–65535.
- Normalized origin = (`https`, host lowercased with the terminal `.` removed and
  IPv6 compressed by `ipaddress`, port or 443).

### Generated file names

Every generated basename uses only `[a-z0-9._+-]` (lowercase, so case-insensitive
filesystems cannot alias two names), is at most 200 characters, and is built from
already-validated parts, so no sanitizing step exists that could alias two inputs. The
final path is resolved and must lie under the configured directory, otherwise exit 2.

- fping cache (`netdata.fping_cache_dir`), `+` separates key and target (neither part
  can contain `+`); the target is lowercased (its match is case-insensitive, doc-4):
  - with `--server`: `server-<lowercased name>+<target>.json` (name ≤ 64, target ≤ 64;
    server names are unique case-insensitively, see `[servers]`);
  - with `--host`, when the lowercased host is a DNS name or IPv4 of at most 100
    characters: `host-<host>+<target>.json`;
  - any other host (IPv6, longer names): `hostid-<h>+<target>.json`, `h` = 32 hex
    digits of SHA-256 over the normalized host (collision-resistant, 128 bits). The
    distinct `server-`/`host-`/`hostid-` namespaces never alias each other.
- cloudflare export (`cloudflare.export_dir`): the zone must be a DNS name (HTTPS URLs
  grammar) of at most 150 characters, lowercased; `<zone>.json` (legacy name kept) and
  snapshots `<zone>+<UTC yyyymmddthhmmssz>[-N].json` (lowercase timestamp; `+` cannot
  occur in a zone, so a snapshot never aliases another zone's export; legacy used `-`).
  When the zone's first label is a Windows device name (`con`, `prn`, `aux`, `nul`,
  `com1`–`com9`, `lpt1`–`lpt9`; Windows matches them before the first dot), `<zone>` in
  both names is replaced by `zone+<h>`, `h` = 32 hex digits of SHA-256 over the zone
  (a zone cannot contain `+`, so this namespace never aliases a plain zone).

Required unit tests (in the port tasks that write these files): server `server1` vs
host `server1`; host `2001:db8::1` → `hostid-`; a 253-character host → `hostid-`; name
and target at 64 characters → basename ≤ 200; `a-b`+`c` vs `a`+`b-c`; target `CPU` and
`cpu` → the same file (one logical key); zone `x` snapshot vs zone
`x-20260101t000000z` export differ; zones `con`, `aux.example.com` and `lpt9.example`
→ `zone+<h>` names, `console.example.com` → plain name.

## Top level

| Key | Type | Default | Rule |
|---|---|---|---|
| `schema_version` | integer | required | `1`. Missing → error. Greater than the highest version the installed `cca` supports → error naming both versions. Lower than 1 → error. |

## `[servers.<name>]` — server registry

`<name>` is a name (see General rules); it is the server argument of `cca run`,
`server`, `diagnose`, `netdata --server`, `open-ports --delegate`, and the tmux window
name. Names are unique case-insensitively: two tables differing only in case (`server1`,
`Server1`) are a load-time error. Config order (TOML table order, preserved by `tomllib`) is the order for `--all`
and listings. An empty or missing `[servers]` is valid at load time; commands that need
a server fail at use time.

| Key | Type | Default | Rule |
|---|---|---|---|
| `ssh` | string | the server name | ssh destination `[user@]host`: user `^[A-Za-z0-9_][A-Za-z0-9._-]*$`, host `^[A-Za-z0-9][A-Za-z0-9._-]*$` (ssh config alias, hostname or IPv4). Never starts with `-`; passed as one argv element after `--`. Ports and options belong in the user's ssh config. |
| `netdata_host` | string | – | Hostname, IPv4 or IPv6 literal (without brackets). Required at use time by `cca netdata` for this server. |
| `netdata_port` | integer | `19999` | 1–65535. |
| `netdata_transport` | string | `"ssh"` | `"ssh"` (curl on the server through `ssh`) or `"direct"` (HTTP from the local machine). |

## `[run]` — `cca run` and the executor

| Key | Type | Default | Rule |
|---|---|---|---|
| `transport` | string | `"tmux"` | `"tmux"` or `"ssh"`. |

### `[run.tmux]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `session` | string | – | tmux session name, `^[A-Za-z0-9_-]+$`. Required at use time when `run.transport = "tmux"`. No name is derived from the directory. |
| `tokf` | boolean | `false` | Pass completed command output through `tokf` (resolved lazily from PATH; missing `tokf` → output unprocessed, as legacy). |

### `[run.log]` — command log

Presence of the table enables logging; without it nothing is logged.

| Key | Type | Default | Rule |
|---|---|---|---|
| `dir` | path | `"logs"` | Must exist at use time (cca never creates it); missing → error naming the path. |
| `operator` | string | required | Name of the operator in the log file name and lines, `^[A-Za-z0-9][A-Za-z0-9._-]*$`. |

Log file `<dir>/<YYYY-MM-DD>-<operator>.log`; line format and secret sanitizing are
decided in TASK-1.4 from the legacy behavior.

## `[secrets]` — sops file locations

| Key | Type | Default | Rule |
|---|---|---|---|
| `curl` | path | `"secrets/curl.secret.yaml"` | Used by `cca curl` and by every command that calls an HTTP API through it (`hetrix`). |
| `cloudflare` | path | `"secrets/cloudflare.secret.yaml"` | Used by `cca cloudflare`. |

Paths resolve from the config dir. The file is opened only by a command that needs the
secret (doc-1 "Secrets").

## `[netdata]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `fping_cache_dir` | path | `"server-logs/fping"` | Directory of `fping --history` caches; file names in "Generated file names". **Intentional change**: legacy `<server-or-host>-<target>.json` caches are not reused (refetched once). Created on first write. |
| `fping_target` | string | – | Default `fping --history --target`; `^[A-Za-z0-9][A-Za-z0-9._-]*$`, at most 64 characters; the same rule applies to the CLI `--target` (exit 2). Absent → `--target` is required for `--history`. |

## `[cloudflare]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `export_dir` | path | `"tmp/cloudflare"` | `export`/`diff` default file and pre-write snapshots, file names in "Generated file names". Created on first write. |
| `api_base` | string | `"https://api.cloudflare.com/client/v4"` | An HTTPS URL (see "HTTPS URLs") with an optional path and no query or fragment. Passed explicitly to the SDK client. |

## `[check_domain]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `our_ips` | array of strings | `[]` | Each an IPv4 or IPv6 address (`ipaddress.ip_address`). Empty → the command warns that ownership cannot be verified (legacy behavior). |
| `hosting_marker` | string | – | URL path of the hosting marker file. One leading `/` is stripped; the rest must match `^[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*$` and contain no `.` or `..` segment. Absent → marker check reports "not configured". |

## `[server_info]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `net_iface_prefixes` | array of strings | `["en", "eth"]` | Non-empty array; each `^[A-Za-z0-9]+$` (the values build a remote filter, so no regex or shell metacharacters). |

## `[diagnose]`

Both commands run **on the target server** through the executor (remote shell, same
quoting rules as `cca run`). `.cca.toml` is trusted project code (doc-1).

| Key | Type | Default | Rule |
|---|---|---|---|
| `apache_status_cmd` | string | `"apache2ctl"` | Program prefix; `cca diagnose` appends ` fullstatus` as legacy. No control characters. |
| `mongodb_status_cmd` | string | – | Full remote command. Absent → MongoDB section reports "skipped: set diagnose.mongodb_status_cmd". No control characters. |

## `[watchlist]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `file` | path | see rule | Absent → first existing of `cca/watchlist.json`, `watchlist.json` (config dir); none exists → `cca/watchlist.json` when the `cca/` directory exists, else `watchlist.json`. |

## `[legacy]` — `cca doctor --legacy`

| Key | Type | Default | Rule |
|---|---|---|---|
| `include` | array of strings | `[]` | Extra files to scan besides git-tracked files. |
| `allow` | array of strings | `[]` | Files whose findings are reported as allowed (migration notes). |

Patterns are relative to the config dir and use `/`; absolute patterns and `..`
segments are errors. Matching is glob-compatible: `*`, `?` and `[…]` match within one
path segment (`fnmatch.fnmatchcase`, hidden names included), `**` as a whole segment
matches zero or more segments. Files are enumerated by walking the config dir with
`os.walk(followlinks=False)`; directory symlinks are pruned before descent and counted,
so expansion never leaves the config dir and cannot loop. A line containing `cca-legacy-ok` is
always reported as allowed.

**Default exclusion list** (not scanned for content, even when tracked or included):
`.git/**`, `**/node_modules/**`, `**/.venv/**`, `**/venv/**`, `**/__pycache__/**`,
`logs/**`, `server-logs/**`, `backlog/completed/**`, `backlog/archive/**`, `*.log`.
Binary files (NUL byte in the first 8 KiB), symlinks and files over 2 MiB are skipped
and counted in the report. The exclusion list never applies to the probes below.

**Containment** (every content read: tracked, included and known-path files): a file is
read only when no component of its path below the config dir is a symlink (checked with
`lstat` per component, so `docs/link/file.md` with `docs/link` a directory link is
skipped) and its `os.path.realpath` lies under the config dir. A skipped link is counted in the report; a known legacy path that exists only through a
link is reported as present but not read. Regression tests in TASK-1.8 cover a linked
directory inside an include pattern, a linked leaf file, and a linked ancestor of a
known-path probe (nested repo reached through a link).

**Known legacy paths**, probed in the project root and every nested repo regardless of
git tracking and exclusions: `.cca-env`, `.cca-env.local`, `.env`, `.env.local`,
`.cca-tmux-cli`, `.tmux-cli-python.yaml`, `.netdata-servers`, and the agent instruction
files `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, `GEMINI.md`,
`.cursorrules`, `.github/copilot-instructions.md`.

**Agent skill install dirs** probed for symlinks (link metadata only, never following a
link to read content): project-relative `.claude/skills`, `.agents/skills`,
`.codex/skills`, `.gemini/skills`, `.opencode/skills`, `.cursor/skills`, `.pi/skills`,
`.github/skills`; user-level `~/.claude/skills`, `~/.agents/skills`, `~/.codex/skills`,
`~/.gemini/skills`, `~/.config/opencode/skills`, `~/.cursor/skills`,
`~/.pi/agent/skills`; and every directory in `PATH`. A link fails the check when its
`os.path.realpath` lies under `<R>/bin` or `<R>/skills` of an **old CCA tree** `R`: a
directory containing both `lib/cca-env.sh` and `bin/cca-run-on-server`. Dangling links
are resolved the same way (realpath of the link text).

## Legacy input mapping

Every input listed in doc-1 "Legacy inputs doc-2 must map", plus inputs found in the
legacy sources. `cca doctor --legacy` reports each name in the left column.

| Legacy input | Read by | v1 |
|---|---|---|
| `CCA_OUR_IPS` (comma list) | `cca-check-domain` | `check_domain.our_ips` (split on `,`, trimmed) |
| `CCA_HOSTING_MARKER` | `cca-check-domain` | `check_domain.hosting_marker` |
| `CCA_APACHE_STATUS_CMD` | `cca-diagnose-gather` | `diagnose.apache_status_cmd` |
| `CCA_MONGODB_STATUS_CMD` | `cca-diagnose-gather` | `diagnose.mongodb_status_cmd`; **intentional change**: legacy ran it locally as a single argv element, v1 runs it on the server like the Apache command (matrix row in TASK-1.3.6) |
| `CCA_NET_IFACE_PREFIXES` (`a\|b` regex) | `cca-server-info` | `server_info.net_iface_prefixes` (split on `\|`) |
| `CCA_LOGGING` | shown by `cca-tmux-cli --doctor` only | dropped: never controlled logging; presence of `[run.log]` does |
| log dir `logs/` (hard-coded, logging when it exists) | `cca-tmux-cli`, `cca-run-on-server` | `run.log.dir`; **intentional change**: logging is explicit, not triggered by the directory |
| `ADMIN_NAME` | `cca-tmux-cli`, `cca-run-on-server`, `cca-doctor` | `run.log.operator` |
| `CCA_AGENT` | `tmux_cli_python` audit | dropped with `tmux_cli_python` (phase 1) |
| `CCA_TMUX_TOKF=1` | `cca-tmux-cli` | `run.tmux.tokf = true` |
| `CCA_WATCHLIST` | `cca-watchlist` | `watchlist.file` |
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
| Cloudflare SDK ambient configuration (env base URL and other SDK defaults) | `cloudflare` SDK in `cloudflare-cli` | dropped; `cloudflare.api_base` is the only explicit replacement, all ambient SDK fallbacks disabled |
| `secrets/curl.secret.yaml` (CWD-relative) | `cca-curl-secret`, `cca-hetrix` | `secrets.curl` (config dir relative) |
| `HETRIX_API_KEY` (comment only, never read) | – | dropped; hetrix uses a `curl` credential |

Not config (doc-1): `CCA_DENYLIST` (bash repo check), `CCA_ENV_FILES`, `CCA_ROOT`,
`CCA_SKILLS`.

## Secrets file shapes

sops files, any input format sops supports; `cca` reads them only through
`sops -d --output-type json FILE` and validates the decrypted JSON below. Validation
errors name the file and the key path, never a value. Unknown keys: warning (key path
only), ignored.

### `secrets.curl` — `cca curl`, `cca hetrix`

```yaml
credentials:
  example_api:
    origins:
      - https://api.example.com
      - https://api.example.com:8443
    bearer: <token>
  example_panel:
    origins: [https://panel.example.com]
    username: <user>
    password: <password>
    csrf: true
```

| Key | Type | Rule |
|---|---|---|
| `credentials` | map | Required, at least one entry. |
| `credentials.<id>` | map | `<id>` matches `^[a-z0-9][a-z0-9_]*$` (legacy ids keep working). |
| `.origins` | array of strings | Required, non-empty. Each an HTTPS URL (see "HTTPS URLs") of the form `https://HOST[:PORT]` with an optional trailing `/` and nothing else (no path, query, fragment, wildcard). Two origins of the **same credential** equal after normalization → duplicate error. Different credentials may share an origin (see selection). |
| `.bearer` | string | Token; sent as `Authorization: Bearer` header; the only value substituted for `{TOKEN}`. |
| `.username`, `.password` | string | Basic auth; `password` requires `username` and vice versa. |
| `.csrf` | boolean | Default `false`. `true` → fetch the CSRF token from the request URL with the same credential before the request (legacy behavior). |

- Exactly one auth form per credential: `bearer`, or `username` + `password`.
- Values must not contain control characters (they are written to a curl config).
- **Credential selection**: the request URL's normalized origin must equal one origin
  of the selected credential. Without `--cred-id`, the credential is the unique one
  whose `origins` contain the request origin; none or more than one → exit 2 listing
  credential ids (with more than one, `--cred-id` picks among them). The request URL is
  validated and normalized by "HTTPS URLs" before matching. **Intentional change**: the legacy hostname-derived id (`api_example_com`,
  then `example_com`) is replaced by the origin match. Credential ids are not secret;
  `cca curl --help` may list them only from sops metadata without decrypting values.
- `cca hetrix` uses the credential matched for `https://api.hetrixtools.com`.

### `secrets.cloudflare` — `cca cloudflare`

```yaml
api_token: <token>
```

| Key | Type | Rule |
|---|---|---|
| `api_token` | string | Required, non-empty, no control characters. Passed explicitly to the SDK client with `cloudflare.api_base`; no SDK environment fallback. |

## Fixtures

- `tests/fixtures/cca-toml/valid/*.toml`: must load without error. `unknown-key.toml`
  must load and warn exactly for the keys listed in its header comment.
- `tests/fixtures/cca-toml/invalid/*.toml`: must fail with exit 2; the header comment
  `# expect: <dotted key>` (or `# expect: syntax`) names what the error must mention.
- `tests/fixtures/sops-shapes/*.json`: decrypted-form secrets documents (what
  `sops -d --output-type json` returns); `valid-*` must validate, `invalid-*` must fail
  naming the key in `tests/fixtures/sops-shapes/README.md`.
- All fixture values are dummies (`server1`, `example.com`, `203.0.113.x`).
