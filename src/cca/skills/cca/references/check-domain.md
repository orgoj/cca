# cca check-domain

Checks whether a domain points to our hosting.

```
cca check-domain DOMAIN
```

Settings from `[check_domain]` in `.cca.toml` (the command also runs without one):
`our_ips` (addresses of our servers) and `hosting_marker` (URL path of the file our web
servers answer with their server name). Without `our_ips` a warning says ownership of
the addresses cannot be told.

Output, in order:

- `CNAME:` steps and every `A:`/`AAAA:` address; ours are marked `(ours)`, any other
  shows its owner from RDAP (network and organization; a known CDN is named, e.g.
  `- CDN Cloudflare`). The owner is informational: `unknown (reason)` never fails the
  check.
- `Marker:` `https://DOMAIN/<hosting_marker>`, fetched from the addresses above. The
  certificate state is shown (`valid` / `invalid: reason`); an invalid certificate does
  not stop the check. Redirects are followed only on the same host.
- `Redirects from http://DOMAIN/:` each hop (status, target, `[HTTP->HTTPS]`), up to 5.
- `Result: CONFIRMED (served by SERVER)` or `Result: NOT CONFIRMED (reason)`.

Exit 0 confirmed; 1 not confirmed (no A/AAAA records, marker missing or invalid,
redirect to another host, marker not configured); 2 usage, configuration or DNS
resolver error.

Example: `cca check-domain www.example.com`
