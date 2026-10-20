# cca hetrix

Reads HetrixTools (API v3): uptime monitors, failures, server agent stats, blacklists.
The API key is the bearer credential for `https://api.hetrixtools.com` in the project's
curl sops file (`[secrets] curl`); exactly one credential must allow that origin.

```
cca hetrix COMMAND [OPTIONS]
```

| Command | Use it to |
|---|---|
| `status` | check that every monitor is UP (exit 1 and the DOWN names otherwise) |
| `down` | see DOWN monitors with the time they went down and their target |
| `all` | see every monitor: UP with duration and uptime %, DOWN with since |
| `response-times` | see response time per location of UP monitors (`slow` > 3 s, `very slow` > 5 s) |
| `outages [--since T] [--until T]` | see monitors whose status changed in a period (default last 24 h; only the last change per monitor) |
| `monitor-outages MONITOR [--since T] [--until T] [--full] [--gap S]` | see failures of one monitor per location, grouped into outage windows split by gaps over S seconds (default 900); `--full` lists every failure; default last 7 days |
| `monitor-info MONITOR` | see one monitor's details including its target |
| `server-stats MONITOR` | see server agent data: system, load, disks (`WARNING` ≥ 80 %, `CRITICAL` ≥ 90 %), RAID |
| `blacklist [TARGET]` | see listed targets, or the blacklists and delist links of one IPv4 address or domain |

- MONITOR is a 32-character monitor id or a case-insensitive part of the name; an exact
  name wins over partial matches.
- Times: `30m`, `12h`, `7d` (ago), or local `YYYY-MM-DD` / `"YYYY-MM-DD HH:MM"`.
- `monitor-outages` reads at most 20 pages of the failure log and says so when older
  failures are missing; narrow the period then.
- `server-stats` needs the API key to allow the server agent metrics call (HTTP 403
  otherwise).
- Exit 1: a monitor is DOWN (`status`), a target is on a blacklist (`blacklist`;
  dnsbl-2/dnsbl-3.uceprotect.net are warnings only, dnsbl-1 counts), or no monitor or
  blacklist monitor matches. Exit 2: API failure (message names the call and the HTTP
  status), configuration or usage error. Rate limits are not retried.

Example: `cca hetrix monitor-outages web --since 3d`

## Outage investigation

1. `cca hetrix status`, then `cca hetrix outages --since YYYY-MM-DD` (the last check);
   one session task per problematic monitor.
2. Before evaluating, find the project's patterns (429/rate limits, known false alarms):
   `tantivy2agents search "hetrix 429"` or similar in the guides.
3. **Decide from the overview first:** is the outage already recorded? Match an incident
   by **date and service** (an incident from Oct 8 does not explain an outage on Oct 15).
   A match: link the incident, done, no detail calls.
4. Only for a new, unrecorded outage, and only when it changes the decision:
   `cca hetrix monitor-outages MONITOR --since YYYY-MM-DD` for the error type (timeout,
   refused, 5xx, keyword; never assumed: they have different causes) and the affected
   locations (`--full` rarely); `cca hetrix monitor-info MONITOR` for the exact target.
   The target URL is **required evidence** for 404/410 results and keyword monitors (it
   tells a removed or changed page from a random outage); otherwise only when you search
   it in the logs.
5. Search that URL in the project's local log data (per its log guide), never by grep on
   the server.
6. Summary: current status (all UP or what is not), each investigated monitor with its
   finding or incident link, new issues that need action.
