# cca asn

Who routes and owns an IP address, where it is and what kind of network it is.

```
cca asn [--json] IP [IP...]
```

Sources: RIPEstat (announced prefix, origin ASNs and holder, RPKI validity, abuse
contacts), ipapi.is (organization, country, city, type flags) and the PTR record. Only
IP addresses are accepted; use `cca check-domain` for names. Runs without a
`.cca.toml`.

Default output, one line per address:

```
1.1.1.1|AS13335|AU|dc,anycast|rpki:valid|Example Org|one.example.net
```

`IP|ASN|COUNTRY|FLAGS|rpki:STATUS|ORGANIZATION|PTR`:

- ASN `AS-` = not announced; several origins (and their RPKI states) joined by `+`.
- FLAGS: the true ones of `dc`, `proxy`, `vpn`, `tor`, `mobile`, `abuser`, `crawler`,
  `anycast`; `-` none, `?` unavailable.
- `-` a missing value, `?` a source failed (named on stderr). `|` inside a value is
  printed as `/`.
- Private, loopback and other non-global addresses print `IP|bogon` with no lookup.

`--json` prints one array with every field (also `abuse_contacts`, `city`, the `asns`
holders and per-source `errors`); bogons are `{"ip": ..., "bogon": true}`.

ipapi.is key: the bearer value of the credential for `https://api.ipapi.is` in the
project's curl secrets file (sent only in a POST body). Without it the lookup is
keyless: no type flags, a country name instead of the code, 30 lookups a day per
client address.

Exit 0 every source answered; 1 a source failed for an address (quota, timeout, PTR
resolver failure; a missing PTR is not a failure); 2 usage or configuration error.

Example: `cca asn 203.0.113.7 2001:db8::1` (documentation ranges print `bogon`).
