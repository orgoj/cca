# cca cloudflare

Reads and changes Cloudflare zones of the project's account: DNS records, WAF custom
rules, zone audit, security events, traffic, exports.

```
cca cloudflare GROUP COMMAND [ARGS]
```

- The API token comes only from the sops file `secrets.cloudflare` (key `api_token`),
  which must lie inside the project (no absolute path or symlink outside); `CLOUDFLARE_*`
  environment variables are ignored. The endpoint is always
  `https://api.cloudflare.com/client/v4`.
- Write commands only print a plan; `--apply` changes Cloudflare. Before the write a
  snapshot goes to `cloudflare.export_dir`: for WAF the zone export
  `ZONE+<UTC time>.json`, for DNS a `dns dump-zone` file `ZONE+<UTC time>.dns.json`
  (a `restore-zone` input); a failed snapshot writes nothing. Every write is then read
  back; a mismatch or a rejected write exits 1. For DNS both name the `restore-zone`
  command for the snapshot, and a rejected write also lists what was already applied. A plan without
  changes writes no snapshot.
- Target WAF rules with the rule id from `waf list`; a position (`3`) works only in a
  plan, an exact description must be unique.

DNS writes:

- `dns ensure-cname`: creates or updates one CNAME, TTL auto. Proxy: an existing record
  keeps its state unless `--proxied` or `--dns-only` is given; a new record is DNS-only
  unless `--proxied`. Check `proxied=` in the plan before `--apply`. A record of another
  type at the name (e.g. apex A records) is a `CONFLICT` (exit 1); no command deletes it.
- `dns ensure-dkim`: CNAMEs `S._domainkey.ZONE` → `S._domainkey.T`, always DNS-only.
- `dns restore-zone FILE`: records match by name, type and content. Missing → `CREATE`;
  ttl/proxied/priority differ → `UPDATE`; a live record that blocks a create by the
  CNAME rule (same name, one of them a CNAME) → `REPLACE` (deleted before the create),
  so a changed CNAME rolls back to the dump. Other live records not in the file are
  kept, or deleted with `--delete-extras` (also verification records added since: use it
  only when the plan lists exactly those). Apply order: deletes, updates, creates.
  `comment`/`tags` are restored on create/update but not compared.
- `dns import D FILE`: BIND zone file with `$ORIGIN`, `$TTL`, `( )` continuation,
  comments, omitted owner (= previous), optional TTL (`3600`, `1h`) and class `IN` (only
  IN). Names without a trailing dot are relative to the current `$ORIGIN` (default: the
  zone; a relative `$ORIGIN` is relative to the previous one). Types A, AAAA (one valid
  address), CNAME (one name), MX (priority + host), TXT (quoted strings, joined, as in a
  split DKIM key); SOA and apex NS are `SKIP`ped (Cloudflare serves them); any other type
  is `UNSUPPORTED`. A record outside the zone, extra or invalid data or another syntax
  error is exit 1 naming the line, before anything is written. A CNAME together with other
  records of its name in the file is a `CONFLICT` for all of them. Per record: equal name,
  type and content live → `OK`, or `UPDATE` when ttl/priority differ (the live proxy
  state is kept); missing → `CREATE` DNS-only with the file's TTL clamped to 60–86400
  (no TTL anywhere → auto); a live record blocking it by the CNAME rule → `CONFLICT`.
  Live records not in the file are listed as `KEEP` and never deleted. Any `CONFLICT` or
  `UNSUPPORTED` → exit 1 and nothing is written, also with `--apply`. Summary
  `--- create= update= ok= conflict= unsupported= skipped= kept= ---`. A re-run is all
  `OK`.
- `zone add D [--account ID]`: plan `CREATE zone D (type full) in account ID (name)`;
  `--apply` creates it, reads it back and prints `nameservers: a, b`; set those at the
  registrar (remove an old DS record first). An existing zone prints `OK zone D exists`
  and its nameservers (exit 0). The account is `--account ID` as given (Cloudflare
  checks it), else the only account the token sees (account list, or the accounts of its
  zones); none or more than one → exit 1 asking for `--account`.
- `dns delete D --name N --type T [--content C] [--all]`: `--name` relative to the zone
  (`@` = apex), `--type` case-insensitive, `--content` matches like `restore-zone` (TXT
  without quoting). The plan lists `DELETE <record>` per match. No match → exit 1;
  several matches without `--content` → `MATCH` lines and exit 1 unless `--all`. SOA and
  NS at the apex are refused (exit 1). `--apply`: snapshot, delete, read-back (records
  gone), then `roll back with: cca cloudflare dns restore-zone <snapshot>`. Check the
  domain file for the record's purpose first.
- `zone aop list [--name S] [--verbose]`, `zone aop set D on|off`: shared Authenticated
  Origin Pulls = zone setting `tls_client_auth` (Cloudflare's global client certificate;
  per-zone certificates are another API, not supported). Turning it on blocks nothing by
  itself: the origin must require and verify the client certificate. It proves the request
  came through Cloudflare, not through this account's zone or WAF. `list` reads every zone
  page across all accounts of the token and prints `AOP tls_client_auth: on= off= error=
  (N zones, M accounts)`, with `--verbose` first a `zone<TAB>account<TAB>value` line per
  zone. A failed read or a value other than on/off is never counted as off: the summary
  and each failed zone with its reason go to stderr as one line, exit 1. `set` targets
  exactly one zone (the same name in two accounts → exit 1) and prints one line: `PLAN`,
  `OK ... unchanged` (nothing written) or `CHANGED ... read-back OK`; the setting is read
  back after the write, a mismatch or a rejected write → exit 1. `--verbose` also prints
  the zone and account id. No snapshot (one value, the line shows the old one).
- Only these write DNS; other A/AAAA/MX/TXT changes are delete + import (or a dump
  restore). Never edit a dump to make a change.

Token permissions (custom token, zone resources = the project's zones; each command
needs its row, a missing one is an HTTP 403, exit 1):

| Permission | Needed by |
|---|---|
| Zone > Zone > Read | every command (zone names resolve through `GET /zones`) |
| Zone > Zone > Edit (account-wide zone resources) | `zone add --apply` |
| Zone > DNS > Read / Edit | `dns` reads / `dns ensure-*`, `restore-zone --apply` |
| Zone > Zone WAF > Read / Edit | `waf list`, `ratelimit list`, `export`, `diff` / `waf add\|edit\|move --apply` |
| Zone > Zone Settings > Read / Edit | `zone info`, `zone settings`, `zone aop`, `uam status`, `export`, `diff` / `zone aop set --apply` |
| Zone > Config Settings > Read | `config list`, `export`, `diff` |
| Zone > Firewall Services > Read | `access list`, `ua list`, `export`, `diff` |
| Zone > Bot Management > Read | `bots status` |
| Zone > Analytics > Read | `events`, `analytics` |
| User > User API Tokens > Read | optional: `token verify` prints the token's policies |

`token verify` itself needs no extra permission and shows whether the token is active.

| Command | Use it to |
|---|---|
| `token verify` | check the token and its policies |
| `zone list [--name S]`, `zone info D`, `zone settings D [--setting K]...` | see zones, plan, audit settings, rule counts with free-plan quotas |
| `zone add D [--account ID]` | create a zone (type full, the account's default plan) and print its Cloudflare nameservers |
| `zone aop list [--name S] [--verbose]`, `zone aop set D on\|off` | count / switch shared Authenticated Origin Pulls (`tls_client_auth`) |
| `dns import D FILE` | create A/AAAA/CNAME/MX/TXT records from a BIND zone file (migration) |
| `dns delete D --name N --type T [--content C] [--all]` | delete records of one name and type |
| `dns list D [--name N] [--type T]` | see every record of the zone, or of one name or type |
| `dns show-domain D...`, `dns show-dkim D...` | see `@`/`www`/`_dmarc` or `_domainkey` records |
| `dns ensure-cname D --name L --target FQDN [--proxied\|--dns-only]` | create or fix one CNAME (`@` = apex) |
| `dns ensure-dkim --selector S... --target-domain T D...` | ensure `S._domainkey.D` → `S._domainkey.T` CNAMEs |
| `dns dump-zone D [-o FILE]`, `dns restore-zone FILE [--delete-extras]` | back up (parent dirs of FILE created) and restore DNS records |
| `waf list D`, `ratelimit list D`, `config list D` | list rules of a phase with quota |
| `waf countries [--name S] [-o FILE]` | compare country lists of WAF rules across zones |
| `waf add D --description X --action A --expression E [--before R\|--after R\|--position N]` | add a WAF rule (actions: block, managed_challenge, js_challenge, challenge, log) |
| `waf edit D --rule R [...]`, `waf move D --rule R --before R\|--after R\|--position N` | change or reorder a WAF rule |
| `access list D`, `ua list D`, `uam status D`, `bots status [D] [--raw]` | see IP access, user agent, Under Attack and bot settings |
| `events D [--since 2h] [--raw]` | security events (24 h on the free plan); warns when search engine crawlers were hit |
| `analytics D [--since 24h] [--by hour\|day]` | requests, visits, bytes; windows over 1 day use daily totals |
| `export D [-o FILE]`, `diff D [-i FILE]` | save the zone state to `cloudflare.export_dir/D.json`, compare it with the live zone |

- `--since`: `30m`, `2h`, `1d` or an ISO time (UTC when no zone is given).
- Exit 1: API error, zone not found, conflict in `ensure-*`, rejected write, read-back
  mismatch, `diff` with changes. Exit 2: usage, configuration or missing secret.

Example: `cca cloudflare waf move example.com --rule <id> --before <id>` (plan), then
the same with `--apply`.
