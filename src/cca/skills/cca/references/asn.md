# cca asn

Who routes and owns an IP address, which range is registered for it, where it is and
what kind of network it is.

```
cca asn [--json] IP [IP...]
```

Sources: RIPEstat (announced prefix, origin ASNs and holder, RPKI validity, abuse
contacts), RDAP of the regional registries (the registered range, keyless), ipapi.is
(organization, country, city, type flags) and the PTR record. Only IP addresses are
accepted; use `cca check-domain` for names. Runs without a `.cca.toml`.

Default output, one line per address:

```
1.1.1.1|AS13335|AU|dc,anycast|rpki:valid|Example Org|one.example.net|net:1.1.1.0/24
```

`IP|ASN|COUNTRY|FLAGS|rpki:STATUS|ORGANIZATION|PTR|net:CIDRS`:

- ASN `AS-` = not announced; several origins (and their RPKI states) joined by `+`.
- FLAGS: the true ones of `dc`, `proxy`, `vpn`, `tor`, `mobile`, `abuser`, `crawler`,
  `anycast`; `-` none, `?` unavailable.
- `net:` the range registered for the address at its registry (RIR inetnum/inet6num,
  the legacy `net_range`), as CIDRs joined by `+`. It is **not** the announced BGP
  prefix (`prefix` in `--json`), which can cover a whole operator; which of the two a
  block uses is the project guide's decision.
- `-` a missing value, `?` a source failed (named on stderr). `|` inside a value is
  printed as `/`.
- Private, loopback and other non-global addresses print `IP|bogon` with no lookup.

`--json` prints one array with every field (also `abuse_contacts`, `city`, the `asns`
holders, `registry` with `range`, `cidrs`, `name`, `handle`, `type`, `rir`, and
per-source `errors` and `skipped`); bogons are `{"ip": ..., "bogon": true}`.

ipapi.is key: the bearer value of the credential for `https://api.ipapi.is` in the
project's curl secrets file (sent only in a POST body). Without it the lookup is
keyless: no type flags, a country name instead of the code and a small daily quota.
When that quota is used up (HTTP 429), one warning says so, the remaining addresses
skip ipapi.is (country `?`, organization from the ASN holder, `skipped.ipapi` in JSON)
and the exit status is not affected. With a key, a 429 is a failure.

Exit 0 every source answered (a skipped keyless ipapi.is included); 1 a source failed
for an address (timeout, RDAP or RIPEstat error, keyed quota, PTR resolver failure; a
missing PTR is not a failure); 2 usage or configuration error.

Example: `cca asn 203.0.113.7 2001:db8::1` (documentation ranges print `bogon`).
