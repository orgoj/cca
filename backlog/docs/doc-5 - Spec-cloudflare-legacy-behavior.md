---
id: doc-5
title: 'Spec: cloudflare legacy behavior'
type: specification
created_date: '2026-10-15 09:23'
---

# `cloudflare-cli` (legacy) → `cca cloudflare`

Behavior of the Python script `cloudflare-cli` from a private consumer project, captured
for the port (TASK-1.2.3). Texts of the original are Czech; messages below are
paraphrased in English. Nothing here names consumer zones, accounts or hosts.

## Runtime and credentials

- Python with the `cloudflare` SDK (Cloudflare API v4, `https://api.cloudflare.com`).
  Before importing, the script optionally activates the project venv through a helper
  located relative to the script file. Missing SDK → error, exit 1.
- Token lookup: env `CLOUDFLARE_API_TOKEN`, else the first non-empty
  `CLOUDFLARE_API_TOKEN=` line in `.cca-env.local`, `.cca-env`, `.env.local`, `.env`
  (in that order) in the project root, which is derived from the **script path**, not
  the CWD. Quotes stripped. None → error, exit 1.
- Client: `Cloudflare(api_token=TOKEN)`; other SDK defaults (env base URL etc.) untouched.
- Zone listing: `zones.list(per_page=50)` and the returned page object is iterated to the
  end; whether that auto-paginates depends on the SDK version (not pinned by the source).

## Commands

Grammar: `cloudflare-cli GROUP COMMAND [ARGS]`. Write commands default to **plan**; a
change happens only with `--apply`.

### Read-only

| Command | Arguments | Output |
|---|---|---|
| `token verify` | – | Token id, status, expiry; its policies (effect, permission groups, resources) from the account token list; if listing is not permitted, prints a notice and returns |
| `zone list` | `[--name SUBSTR]` | `name<TAB>status<TAB>zone_id` per zone (zones listed with `per_page=50`, see Zone listing), count line |
| `zone info` | `DOMAIN` | Zone id, status, plan, paused, nameservers; audit settings; rule counts with free-plan quotas (WAF custom 5, rate limiting 1, configuration 10), IP access and UA rule counts |
| `zone settings` | `DOMAIN [--setting KEY]...` | `key: value` for all or selected settings; missing key reported as unavailable on this plan |
| `dns show-domain` | `DOMAIN...` | Records for `@`, `www`, `_dmarc` (missing ones flagged) |
| `dns show-dkim` | `DOMAIN...` | All records whose name contains `._domainkey.` |
| `dns dump-zone` | `DOMAIN [-o FILE]` | JSON `{"schema": "cloudflare-dns-dump/1", "exported_at", "zone": {id, name}, "records": [...]}` sorted by name/type/content; fields name, type, content, ttl, proxied, priority, data, comment, tags (nulls dropped). Stdout, or FILE plus a `DUMP n records -> FILE` line |
| `waf list`, `ratelimit list`, `config list` | `DOMAIN` | Rules of the phase (`http_request_firewall_custom`, `http_ratelimit`, `http_config_settings`) with count/quota: action, disabled flag, description, id, expression, action parameters, ratelimit |
| `waf countries` | `[--name SUBSTR] [-o FILE]` | Across all listed zones: country codes used in WAF custom rule expressions (`ip.src.country` / `ip.geoip.country in {...}`), per zone with actions, union, per-country coverage with missing zones; optional JSON `{generated_at, union, per_zone}` |
| `access list` | `DOMAIN` | IP access rules: mode, target, value, notes |
| `ua list` | `DOMAIN` | User-agent rules (empty if the legacy endpoint fails) |
| `uam status` | `DOMAIN` | Global `security_level` (under attack yes/no), challenge TTL, browser check; configuration rules that set `security_level=under_attack` |
| `bots status` | `[DOMAIN] [--raw]` | Per zone (all listed zones without DOMAIN): account name and AI-crawler / bot-fight fields from `bot_management`; `--raw` prints the full JSON |
| `events` | `DOMAIN [--since 2h] [--limit 1000] [--raw]` | Security events via GraphQL `firewallEventsAdaptive`; `--since` older than 24 h − 1 min is clamped with a notice (free-plan retention). Summary: warning if declared search-engine crawlers were hit, counts by action/source/country, top paths; `--raw` one line per event |
| `analytics` | `DOMAIN [--since 24h] [--by hour|day] [--limit 200] [--no-breakdown]` | Window ≤ 1 day: `httpRequestsAdaptiveGroups` by `datetimeHour` → requests, visits, bytes, per-bucket bars, breakdowns by country, HTTP status, cache status (15 each). Window > 1 day: `httpRequests1dGroups` daily → requests, summed daily uniques, bytes, threats, per-day rows (`--by` and breakdowns ignored) |
| `export` | `DOMAIN [-o FILE]` | Writes zone state JSON (see Files), prints path and counts |
| `diff` | `DOMAIN [-i FILE]` | Unified diff of the stored export vs live state, ignoring `exported_at`; no diff → `OK` line |

`--since` accepts `Nm`, `Nh`, `Nd` or an ISO time (naive = UTC); anything else → error,
exit 1.

### Write (plan by default, `--apply` to change)

Every write command prints `MODE: plan|apply` or a plan header and, without `--apply`,
ends with "PLAN — nothing changed in Cloudflare".

- `dns ensure-dkim --selector S [--selector S]... --target-domain T DOMAIN... [--apply]`:
  for each zone and selector ensure CNAME `S._domainkey.ZONE` → `S._domainkey.T`,
  ttl 1 (auto), not proxied.
- `dns ensure-cname DOMAIN --name LABEL --target FQDN [--apply]`: one CNAME
  (`@` = apex), ttl 1, not proxied, trailing dot of target stripped.
  Both ensure commands print `OK`, `CREATE` or `UPDATE` (from/to); a record of another
  type with that name, or more than one record of the type, prints `CONFLICT` and the
  command exits 1 after processing all records.
- `dns restore-zone FILE [--domain D] [--delete-extras] [--apply]`: requires schema
  `cloudflare-dns-dump/1`; zone from `--domain` or the file. Records matched by
  (name, type, content without trailing dot): missing → `CREATE`; ttl/proxied/priority
  differ → `UPDATE`; extras → `DELETE` only with `--delete-extras`, otherwise counted as
  kept. Summary `create= update= ok= delete= extras_kept=`.
- `waf add DOMAIN --description D --action A --expression E [--before R | --after R |
  --position N] [--disabled] [--apply]`
- `waf edit DOMAIN --rule R [--description D] [--expression E] [--action A]
  [--enable | --disable] [--apply]`
- `waf move DOMAIN --rule R (--before R | --after R | --position N) [--apply]`

WAF write rules:

- Writable actions: `block`, `managed_challenge`, `js_challenge`, `challenge`, `log`.
- Rule selector R: 32-hex rule id, exact description (must be unique), or 1-based
  position — position is rejected with `--apply` (order may have changed).
- `add` fails when the zone is at the quota (5, disabled rules count); without placement
  the rule goes to the end with a warning. A missing zone entrypoint ruleset (recognized
  only by a 404 with a specific message) is created on `add`; any other read error is
  fatal so an empty list never creates a new ruleset.
- `edit` keeps all writable fields (drops `id`, `version`, `last_updated`, prunes nulls);
  changing the action of a rule with `action_parameters` is refused.
- `move` refuses an anchor equal to the moved rule.
- Header shows account (name, id), zone, phase, ruleset id.
- With `--apply`: first a pre-write zone export (never overwritten; failure aborts
  before any change), then the API write, then a read-back that verifies the written
  fields and the placement; mismatch → error, exit 1.

## Files

Paths derive from the project root (script-relative, see above):

- `export` / `diff` default: `tmp/cloudflare/<domain>.json` (help text wrongly says
  `cca/cloudflare/`). Schema `cloudflare-zone-export/1`: zone (id, name, status), audit
  settings, WAF custom / rate-limit / configuration rules, IP access rules, UA rules,
  DNS records; JSON sorted keys.
- Pre-write snapshot: `tmp/cloudflare/<domain>-<UTC YYYYmmddTHHMMSSZ>[-N].json`.
- `dump-zone -o`, `waf countries -o`, `export -o`, `diff -i`: user paths (CWD-relative).
- Audit settings: `security_level`, `challenge_ttl`, `browser_check`, `pseudo_ipv4`,
  `always_use_https`, `ssl`, `min_tls_version`, `development_mode`, `cache_level`,
  `ipv6`, `email_obfuscation`, `hotlink_protection`.

## Network calls

All to the Cloudflare API with the bearer token: zones list; `GET /zones/{id}/settings`;
`GET /zones/{id}/bot_management`; DNS records list/create/edit/delete; rulesets phase
entrypoint get, ruleset create, rule create/edit; firewall access rules and UA rules
list; user token verify and token list; `POST /graphql` (firewall events, adaptive and
daily HTTP request groups).

## Exit codes

- `0`: success, plan output, `diff` with no change, read-only "no data".
- `1`: `fail()` errors (missing SDK/token, zone not found or ambiguous, bad `--since`,
  GraphQL error, invalid selector, quota, write rejected, read-back mismatch, missing
  export file); `diff` with changes; ensure-* conflicts; uncaught SDK exceptions
  (traceback) in read paths without explicit handling.
- `2`: argparse usage errors.

## External tools

None besides Python and the `cloudflare` SDK.

## Intentional changes for `cca cloudflare`

Settled (doc-1):

- Token only from the project's sops file (shape in doc-2); no `CLOUDFLARE_API_TOKEN`
  env, no `.cca-env`/`.env` parsing; missing → exit 2 naming what is missing. The SDK
  client gets token and base URL explicitly; ambient SDK fallbacks disabled.
- Paths from `.cca.toml` / the CWD, never from the script location; export directory
  configurable (doc-2), default stays `tmp/cloudflare/` under the project root.
- No venv bootstrap; the SDK is a declared dependency of the `cca` package.
- The token never appears in child argv, logs or diagnostics (doc-1 "Secrets").
- English texts; examples use `example.com`.

Proposed, decided in TASK-1.2.3 (each needs a compatibility-matrix row):

- Zone listing: verify against the pinned SDK whether page iteration auto-paginates; the port must list all zones (matrix row with more than one page).
- Uncaught SDK exceptions become clean errors (exit 1) instead of tracebacks.
- Fix the export help text path.
- The search-engine crawler regex in `events` lists generic crawlers only (the legacy
  list includes a regional engine; keep or make configurable).
