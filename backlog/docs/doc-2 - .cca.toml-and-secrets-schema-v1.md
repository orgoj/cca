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

Applies to curl `origins` and every `cca curl` request URL, so
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
  DNS writes save a DNS dump (`cloudflare-dns-dump/1`, `restore-zone` input) as
  `<zone>+<UTC yyyymmddthhmmssz>[-N].dns.json`, distinct from the WAF snapshot by suffix.
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
`server`, `netdata --server`, `open-ports --delegate`, and the tmux window
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
| `aliases` | array of strings | `[]` | Other names for this entry (name rule). Server names and aliases share one case-insensitive namespace: an alias equal to any server name or other alias, or to its own entry's name, is a load-time error. Every command that takes a server (`run -t`, `server`, `netdata --server`, `open-ports -d`, `ioc.hosts` and `ioc` HOST) resolves a name or alias case-insensitively to its entry (a note on stderr for an alias) and then uses the entry name only: ssh target, tmux window, `[run.log]` line, fping cache, ioc state. `--all` and listings iterate entries only; `cca run --list` appends `aliases=a,b`. |

## `[run]` — `cca run` and the executor

| Key | Type | Default | Rule |
|---|---|---|---|
| `transport` | string | `"tmux"` | `"tmux"` or `"ssh"`. Only for `cca run` (the agent's live commands); `cca server` always uses ssh. |
| `tokf` | boolean | `false` | `cca run` passes completed command output (both transports) through `tokf` (resolved lazily from PATH, protocol `cca-v1`; missing, unsupported or failing `tokf` → output unprocessed). |

### `[run.tmux]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `session` | string | – | tmux session name, `^[A-Za-z0-9_-]+$`. Required at use time when `run.transport = "tmux"`. No name is derived from the directory. |

### `[run.log]` — command log

Presence of the table enables logging; without it nothing is logged.

| Key | Type | Default | Rule |
|---|---|---|---|
| `dir` | path | `"logs"` | Must exist at use time (cca never creates it); missing → error naming the path. |
| `operator` | string | the OS login name | Name of the operator in the log file name and lines, `^[A-Za-z0-9][A-Za-z0-9._-]*$`, at most 64. Absent: the OS login name of the cca process, read from the OS (POSIX: the passwd entry of the real uid; Windows: `GetUserNameW`), never from environment variables, so a shared committed `.cca.toml` logs under each admin's name. Resolved before a command runs: an unreadable or non-matching login name is an error naming this key (set `operator`), nothing is executed. `cca config show` prints only a configured value; `cca doctor` shows the effective one and its source. |

Log file `<dir>/<YYYY-MM-DD>-<operator>.log` (created mode 0600, appended, never
through a symlink; a write failure is a warning). One line per executed command, after
it ends, for every command using the executor (`cca run` and the ports using it):
`<ISO-8601 local time> <operator> <server> <command> [exit: <code>|timeout|interrupted]`.
`--create-file` logs `create-file <path>`. The command is masked for likely secrets
(URL userinfo, `key=value`/`key: "value"` for password/token/key/secret names,
`--password VALUE` flags, AWS key ids, GitHub tokens, JWTs, Bearer tokens, database
connection URLs, base64 runs of 40+ characters, private key headers) and kept on one
line (control characters escaped).

## `[secrets]` — sops file locations

| Key | Type | Default | Rule |
|---|---|---|---|
| `curl` | path | `"secrets/curl.secret.yaml"` | Used by `cca curl` and by every command that calls an HTTP API through it (`hetrix`, `asn`). |
| `cloudflare` | path | `"secrets/cloudflare.secret.yaml"` | Used by `cca cloudflare`. Its real path (symlinks resolved) must lie inside the config dir, otherwise exit 2 before sops runs; sops decrypts the checked real path. |

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
| `api_base` | string | `"https://api.cloudflare.com/client/v4"` | **Pinned**: any other value is a load-time error (a config could otherwise send the token to another host). Passed explicitly to the SDK client. |

## `[check_domain]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `our_ips` | array of strings | `[]` | Each an IPv4 or IPv6 address (`ipaddress.ip_address`). Empty → the command warns that ownership cannot be verified. |
| `hosting_marker` | string | – | URL path of the hosting marker file. One leading `/` is stripped; the rest must match `^[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*$` and contain no `.` or `..` segment. Absent → marker check reports "not configured". |

## `[server_info]`

| Key | Type | Default | Rule |
|---|---|---|---|
| `net_iface_prefixes` | array of strings | `["en", "eth"]` | Non-empty array; each `^[A-Za-z0-9]+$` (the values build a remote filter, so no regex or shell metacharacters). |

## `[clean]` — `cca clean`

Cleans only `<config dir>/tmp`; each top-level entry is one unit (a directory by the
newest mtime inside it). The directory of `cloudflare.export_dir` inside `tmp/` is
always kept; `export_dir` equal to `tmp` itself is an error for `cca clean`.

| Key | Type | Default | Rule |
|---|---|---|---|
| `days` | integer | `30` | 1–3650; default of `--days`. |
| `keep` | array of strings | `[]` | Top-level entry names of `tmp/` that are never deleted (exact names, no `/`, no globs). |

## `[ioc]` — `cca ioc`

Reads the state of host-ioc (deployed by the project's role) from `/var/lib/host-ioc/`
on each host; never writes on a host.

| Key | Type | Default | Rule |
|---|---|---|---|
| `hosts` | array of strings | `[]` | Names (see General rules); each must be a `[servers]` entry at use time. Empty → `cca ioc` exits 2. |
| `transport` | string | `"ssh"` | `"ssh"`, or `"run"` = the `run.transport` of `cca run` (projects reaching hosts only through it). |
| `sudo` | boolean | `false` | `true`: every remote script runs as `sudo -n bash -c …` (state is root 0700). |
| `script` | path | – | Local copy of the host-ioc script the role deploys; its SHA-256 is compared with `script_sha256` of each run. Required at use time by `cca ioc status`. |
| `quick_interval_hours`, `deep_interval_hours` | integer | `24` | 1–8760; a run older than twice its interval is a warning. |
| `baseline_dir` | path | `"tmp/host-ioc"` | `cca ioc baseline` writes `<lowercased host>+<UTC yyyymmddthhmmssz>.yaml` (see "Generated file names"), never overwrites; created on first write. |

## Old CCA links — `cca doctor`

`cca doctor` (config required) checks that no old CCA script or skill is still
installed. It reads link metadata only (`lstat`, `os.path.realpath`, `stat` of the two
old-tree marker files), never opens a file, never descends into an entry and never
lists a checked dir whose realpath (itself or a linked ancestor) lies in an old tree;
such a dir under the old `bin/` or `skills/` is reported as one finding.

**Agent skill install dirs**: project-relative (config dir) `.claude/skills`,
`.agents/skills`, `.codex/skills`, `.gemini/skills`, `.opencode/skills`,
`.cursor/skills`, `.pi/skills`, `.github/skills`; user-level `~/.claude/skills`,
`~/.agents/skills`, `~/.codex/skills`, `~/.gemini/skills`, `~/.config/opencode/skills`,
`~/.cursor/skills`, `~/.pi/agent/skills`; and every directory in `PATH` (an empty entry
is the CWD). Each dir itself and its direct symlink entries are checked. A checked dir
or a linked entry is a finding when its `os.path.realpath` lies under `<R>/bin` or
`<R>/skills` of an **old CCA tree** `R`: a directory containing both `lib/cca-env.sh`
and `bin/cca-run-on-server`. This covers a dir reached through a linked ancestor and an
old `bin/` placed directly in `PATH`; a checked dir elsewhere inside `R` is neither
reported nor listed. Dangling links are resolved the same way (realpath of the link
text). A checked dir that cannot be listed is reported at the dir's severity. Findings in project dirs are FAIL; in user-level and
`PATH` dirs WARN, because those stay shared until every consumer project is converted.

Project scripts, docs and agent instructions are not scanned: consumer projects are
converted once by hand (TASK-4) using the migration guide (doc-6).

## Legacy input mapping

Every legacy variable and file is mapped to its v1 key, or marked dropped, in doc-6
"Legacy inputs".

## Secrets file shapes

sops files, any input format sops supports; `cca` reads them only through
`sops -d --output-type json FILE` and validates the decrypted JSON below. Validation
errors name the file and the key path, never a value. Unknown keys: warning (key path
only), ignored.

### `secrets.curl` — `cca curl`, `cca hetrix`, `cca asn`

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
- `cca asn` uses the credential matched for `https://api.ipapi.is` when one exists
  (optional; `bearer` = ipapi.is API key, sent only in the POST body). No secrets file
  or no matching credential → keyless lookup with a warning; more than one → exit 2.

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
