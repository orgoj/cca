---
id: doc-4
title: 'Spec: netdata legacy behavior'
type: specification
created_date: '2026-10-15 09:23'
---

# `netdata-cli.py` (legacy) → `cca netdata`

Behavior of the Python script `netdata-cli.py` (stdlib only) from a private consumer
project, captured for the port (TASK-1.2.2). Texts of the original are Czech; messages
below are paraphrased in English. Nothing here names consumer hosts or targets.

## Invocation

```
netdata-cli [--host H] [--port P] [--server NAME] [--transport ssh|direct] COMMAND ...
```

| Global option | Default | Effect |
|---|---|---|
| `--host` | `localhost` | Netdata host when `--server` is not given |
| `--port` | `19999` | Netdata port when `--server` is not given |
| `--server` | – | Name looked up in `.netdata-servers` (overrides `--host`/`--port`) |
| `--transport` | `ssh` | With `--server`: `ssh` (curl on the server over ssh) or `direct` (HTTP from the local machine) |

No COMMAND: print help, exit 1.

## Server map: `.netdata-servers`

- Lookup: walk up from **two directories above the script file** (not the CWD) to `/`
  (exclusive); first `.netdata-servers` wins. Not found → `Error: .netdata-servers not
  found`, exit 1.
- Format: whitespace-separated columns, `#` comments and blank lines skipped:
  `NAME HOST[:PORT] [SSH_HOST]`. Lines with fewer than 2 columns are ignored. Port
  defaults to 19999. With `--server`, a non-integer or out-of-range port → error,
  exit 1 (for `fping --all` see below).
- Unknown `--server` → error naming the file, exit 1.
- `--transport ssh` with no third column for that server → error suggesting
  `--transport direct`, exit 1.
- On success prints `Using server NAME -> [ssh SSH_HOST ->] HOST:PORT` to **stderr**.

## Transport and network

All calls are HTTP GET `http://HOST:PORT/api/{v1|v3}/...` (no TLS, no auth).

- direct: `urllib.request.urlopen(url, timeout=10)`.
- ssh: `ssh SSH_HOST "<shlex-joined curl -fsS --max-time 10 URL>"`, subprocess timeout
  25 s; the server's own curl reaches netdata on HOST:PORT (netdata is bound to the
  server's VPN address, reachable from the server itself without local VPN).
- Any fetch error (HTTP error, ssh non-zero, ssh timeout, invalid JSON) prints
  `Error fetching URL: <detail>` to stderr and exits 1.
- Endpoints used: `v1/charts`; `v3/data` with `scope_contexts`, `after`, `before`,
  `points`, `time_group`, `group_by`, `instances`, `dimensions`, `format=json`.

## Time arguments (`--after`, `--before`)

All absolute forms are interpreted in **UTC**:

- `-N` → passed as relative seconds (netdata semantics).
- `today HH[:MM]`, `yesterday HH[:MM]`, `HH:MM` → that time today/yesterday.
- `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `YYYY-MM-DD` → Unix timestamp.
- Anything else → uncaught `ValueError` traceback, exit 1.

## Commands

| Command | Arguments (defaults) | Output |
|---|---|---|
| `list` | `[--pattern S]` | No pattern: top 15 context prefixes by chart count, total, usage hints. Pattern (case-insensitive substring of chart id): table `Chart ID / Title / Context` |
| `query` | `--context C` (required), `--after -300`, `--before` | Raw `v3/data` JSON, indent 2 |
| `stats` | `--context C` (required), `--after -3600`, `--before`, `--aggregation min|max|avg` (`max`), `--points 24`, `--instance`, `--dimension` | Table `time | label...`; without `--dimension`, columns auto-picked by keywords (load, cpu, disk, net, ram, mem, req, bytes; label < 40 chars), fallback first column |
| `top` | `--context C` (required), `--after -3600`, `--before`, `-n/--n 20`, `--aggregation` (`max`), `--points 24`, `--group-by dimension|instance|label|node` (`dimension`) | Ranked `label / total / avg`; labels with ≥ 2 dots are "domains" (marked `*`, ranked first); other labels filtered by a skip-word list unless `--group-by instance` |
| `fping` | see below | Latency / packet-loss report |
| `discover` | `QUESTION` (positional) | Suggested contexts from a keyword map (load, cpu, memory, disk, network, web, request, vhost, top) plus charts whose context prefix or title occurs in the question |
| `meta` | `--context C` (required) | Per matching chart: title, units, family, type, first 10 dimensions, labels of a 5-point sample (`after=-300`) |

- `--points` > 1000 → `Error: --points max 1000` on stderr, exit 1 (`stats`, `top`).
- Empty results print a message and exit 0.
- The built-in epilog shows `stats CONTEXT` as positional, but `--context` is required
  (the epilog example fails); the `list` hint mentions a nonexistent `--group` option.

### `fping`

Options: `--after -900`, `--before`, `--threshold 100.0` (ms), `--all`, `--per-target`,
`--history`, `--target SUBSTR` (default: a consumer-specific target name),
`--min-seconds 60`, `--cache PATH`, `--refresh`, `--exclude-hours H[,H...]` (UTC hours).

- Default (window): `fping.latency` min/max columns over all targets → baseline (median
  of minima under threshold), peak max, peak min; "shared path" event when peak min >
  max(threshold/2, 3 × baseline). Always also queries `fping.quality`
  (`group_by=instance`) for packet loss: worst quality, contiguous loss window around the
  worst bucket, seconds at 0 %, affected targets, whether all targets were hit. Up to
  20 over-threshold buckets listed.
- `--per-target`: `group_by=instance` latency, per target baseline/peak, localization
  verdict (some targets bad vs all bad). No packet-loss query.
- `--history`: default `--after` becomes `-7776000` (90 days) when left at `-900`. One
  pull of `fping.latency` grouped by instance (`group_by=instance`), columns whose label contains `--target`
  (case-insensitive), series = max over matching columns. Cached as JSON
  `{"host", "target", "series": [[ts, value], ...]}`; default cache path
  `server-logs/fping/<server-or-host>-<target>.json` relative to the **CWD**; an existing
  cache is read unless `--refresh`; unreadable cache → refetch. Events = contiguous runs
  above threshold lasting ≥ `--min-seconds` (duration quantized to median sample step);
  report per month and the 12 worst events; coarse-resolution warning when step > 90 s.
- `--all`: iterates every `.netdata-servers` entry with **direct transport** (the ssh
  column and `--transport` are ignored), timeout 12 s; per server one summary line with
  tag `OUTAGE!` (100 % loss), `LOSS!`, `NET!` (shared path), `max`, `ok`, or
  "unreachable / no fping" (fetch errors of a server are caught per server); then loss
  details for every server with loss. The "correlated network event" verdict is printed
  when **any one** server has a shared-path event, not only when several do. With
  `--history` one trend line per server. Exit 0 after the scan; a malformed `HOST:PORT`
  in the map (non-integer port) or a malformed `--exclude-hours` raises before the
  per-server error handling → traceback, exit 1. An out-of-range integer port is not
  validated: it goes into the URL, the fetch failure shows as "unreachable" (or
  `--history` reads an existing cache without fetching), and the scan exits 0.
- `--exclude-hours` must be comma-separated integers, otherwise uncaught traceback.

## Exit codes

- `0`: success, including "no data" messages and a completed `fping --all` scan (also
  when servers were unreachable).
- `1`: no command; `.netdata-servers` / server / ssh host missing; invalid port in map;
  fetch error; `--points` > 1000; uncaught exceptions (bad time format, bad
  `--exclude-hours`, non-integer port in the map during `fping --all`).
- `2`: argparse usage errors (unknown option, missing required option, bad choice).

## Files

- Reads `.netdata-servers` (see above); reads/writes the fping history cache.
- Nothing else; no secrets.

## External tools

- `ssh` (user's ssh config/agent) for the ssh transport; remote side needs `curl`.
- No local tools for direct transport.

## Intentional changes for `cca netdata`

Settled (doc-1):

- `.netdata-servers` is replaced by `[servers.<name>]` in `.cca.toml` (netdata address,
  port, ssh target); mapping defined in doc-2. Discovery is the `.cca.toml` walk from the
  CWD, never relative to the script file.
- The ssh transport uses the core ssh helper (`cca.ssh`, TASK-1.1); ssh target validated
  and passed as separate argv. Moving onto the `cca run` executor (TASK-1.4) is a later
  refactor, not a requirement of this port.
- English texts; examples use `server1`, `example.com`, `203.0.113.x`.
- No secrets involved; no environment variables read.

Proposed, decided in TASK-1.2.2 (each needs a compatibility-matrix row):

- `fping --history --target`: no consumer-specific default; the default target comes
  from `.cca.toml` or the option becomes required.
- History cache directory configurable in `.cca.toml` (default stays a CWD-relative
  path).
- `fping --all` honors the configured transport per server instead of always going
  direct; `--all` follows doc-1 semantics where applicable.
- Correlated-event verdict only when at least two servers show a shared-path event.
- Bad time / `--exclude-hours` values → usage error (exit 2) instead of a traceback.
- Fix the help examples (`--context` is required; drop the `--group` hint).
- "Using server ..." line stays on stderr.
