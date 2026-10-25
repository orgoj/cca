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
  back; a mismatch or a rejected write exits 1, and a rejected DNS write lists what was
  already applied and the `restore-zone` command for the snapshot. A plan without
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
- Only these write DNS; A/AAAA/MX/TXT values can be written only by restoring a dump.
  Never edit a dump to make a change.

Token permissions (custom token, zone resources = the project's zones; each command
needs its row, a missing one is an HTTP 403, exit 1):

| Permission | Needed by |
|---|---|
| Zone > Zone > Read | every command (zone names resolve through `GET /zones`) |
| Zone > DNS > Read / Edit | `dns` reads / `dns ensure-*`, `restore-zone --apply` |
| Zone > Zone WAF > Read / Edit | `waf list`, `ratelimit list`, `export`, `diff` / `waf add\|edit\|move --apply` |
| Zone > Zone Settings > Read | `zone info`, `zone settings`, `uam status`, `export`, `diff` |
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
