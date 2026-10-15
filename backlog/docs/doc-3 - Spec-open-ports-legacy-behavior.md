---
id: doc-3
title: 'Spec: open-ports legacy behavior'
type: specification
created_date: '2026-10-15 09:23'
---

# `check-open-ports` (legacy) → `cca open-ports`

Behavior of the bash script `check-open-ports` from a private consumer project, captured
for the port (TASK-1.2.1). Written from the source; nothing here names consumer hosts.

## Invocation

```
check-open-ports [OPTIONS] HOST [PORT...]
```

Options are parsed in a loop until the first non-option argument or `--`; options after
HOST are not recognized (they become ports).

| Option | Argument | Effect |
|---|---|---|
| `-d`, `--delegate` | HOST | Prefix every probe command with `ssh HOST` (scan runs on that host). |
| `-k`, `--kubernetes` | – | Port list = default ports + Kubernetes ports. Ignored when ports are given positionally. |
| `-m`, `--method` | METHOD | `nmap` (default), `nc`, `telnet`, `curl`. |
| `-n`, `--noact` | – | Dry run: print each command instead of running it (prefix `echo`). |
| `-x`, `--xdebug` | – | `set -x`. |
| `-h`, `--help` | – | Print usage, exit 0. |
| `--` | – | End of options. |
| `-*` other | – | Print `Unknown argument '<arg>'`, exit 1. |

- Default ports: `20 22 25 80 443`.
- Kubernetes ports (added by `-k`): `2379 2380 5473 6443 8472 9345 10250 10257 10259`.
- Positional ports after HOST replace the whole list (also the `-k` list).
- Missing HOST: prints `ERROR: Require host.` plus usage, exit 1.
- Option values are not validated: an explicit empty argument (`--method ''`) is
  accepted. An omitted value (option as the last argument) runs a failing `shift` under
  `set -e` and exits 1 without a message.

## Probe commands

Each command is prefixed with `ssh DELEGATE` when `--delegate` is set; the prefix is an
unquoted shell word list, so DELEGATE is word-split by bash.

| Method | Command | Per port? |
|---|---|---|
| `nmap` | `nmap -Pn --reason -p P1,P2,... HOST` | No: one call, ports joined by commas |
| `nc` | `nc -zv -w 5 HOST PORT` | Yes; failures ignored (`|| :`) |
| `telnet` | `telnet HOST PORT` | Yes; interactive, does not terminate on its own |
| `curl` | `curl -s --connect-timeout 5 -o /dev/null http://HOST:PORT` | Yes |
| unknown | nothing is run | – |

## Output

Only the raw output of the probe tool (stdout/stderr pass through). No own summary,
no files written. In `--noact` mode each would-be command line is printed instead.

## Exit codes

The script runs with `set -e`:

- `0`: help; every probe returned 0; `nc` method (failures ignored); unknown method
  (silently does nothing).
- `1`: unknown option, missing HOST.
- Otherwise the exit status of the first failing probe command: `nmap` failing to run,
  `ssh` failure, or `curl` failing on a port (e.g. connection refused) — `curl` stops
  at the first closed port and the remaining ports are not probed.

## External tools and network

- Local or on the delegate: `nmap`, `nc`, `telnet` or `curl` depending on method;
  `ssh` for `--delegate` (user's ssh config and agent).
- Network: TCP connections from the local machine or the delegate host to HOST on each
  port; `curl` sends a plain HTTP request to `http://HOST:PORT`.
- No config files, no secrets.

## Intentional changes for `cca open-ports`

Settled (doc-1):

- English texts; examples use `server1`, `example.com`, `203.0.113.x`.
- Config only from `.cca.toml`; no environment variables. The delegate is a server name
  from `[servers]`, run over ssh with the core ssh helper (`cca.ssh`, TASK-1.1): target
  validated, separate argv, no shell-built `ssh` string. Moving onto the `cca run`
  executor (TASK-1.4) is a later refactor, not a requirement of this port.
- External tools are checked lazily: a missing `nmap`/`nc`/`curl` gives a clear error
  naming the tool.

Proposed, decided in TASK-1.2.1 (each needs a compatibility-matrix row):

- Reject an unknown `--method` with exit 2 instead of silently doing nothing.
- `curl` method: probe every port and report each result instead of stopping at the
  first closed port; non-zero exit when any probe failed.
- `telnet` method: drop it or give it a timeout; it never terminates by itself.
- Options accepted after HOST (argparse), ports validated as 1–65535.
- `-x/--xdebug` has no Python equivalent; drop it.
