# cca cloudflare

Reads and changes Cloudflare zones of the project's account: DNS records, WAF custom
rules, zone audit, security events, traffic, exports.

```
cca cloudflare GROUP COMMAND [ARGS]
```

- The API token comes only from the sops file `secrets.cloudflare` (key `api_token`);
  `CLOUDFLARE_*` environment variables are ignored. The API endpoint is
  `cloudflare.api_base`.
- Write commands only print a plan; `--apply` changes Cloudflare. Before a WAF write a
  zone snapshot goes to `cloudflare.export_dir` (`ZONE+<UTC time>.json`); the write is
  then read back and verified.
- Target WAF rules with the rule id from `waf list`; a position (`3`) works only in a
  plan, an exact description must be unique.

| Command | Use it to |
|---|---|
| `token verify` | check the token and its policies |
| `zone list [--name S]`, `zone info D`, `zone settings D [--setting K]...` | see zones, plan, audit settings, rule counts with free-plan quotas |
| `dns show-domain D...`, `dns show-dkim D...` | see `@`/`www`/`_dmarc` or `_domainkey` records |
| `dns ensure-cname D --name L --target FQDN` | create or fix one CNAME (`@` = apex) |
| `dns ensure-dkim --selector S... --target-domain T D...` | ensure `S._domainkey.D` → `S._domainkey.T` CNAMEs |
| `dns dump-zone D [-o FILE]`, `dns restore-zone FILE [--delete-extras]` | back up and restore DNS records |
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
