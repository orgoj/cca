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

`--json` prints one array, one element per address in argument order.

JSON contract (stable: a key is never renamed or removed, and a value never changes its
type, without a note in the release; new keys may be added, so ignore unknown keys):

- A bogon is exactly `{"ip": "10.0.0.1", "bogon": true}`, with no lookup and no other key.
- A public address always has every key below. A source that failed or was skipped
  leaves its fields `null`; nothing is `"?"` or missing in JSON.

```json
{
  "ip": "1.1.1.1",
  "bogon": false,
  "reverse": "one.example.net",
  "announced": true,
  "prefix": "1.1.1.0/24",
  "asns": [{"asn": 13335, "holder": "EXAMPLE-NET - Example, Inc."}],
  "rpki": [{"asn": 13335, "status": "valid"}],
  "abuse_contacts": ["abuse@example.com"],
  "organization": "Example Org",
  "country": "Australia",
  "city": "Brisbane",
  "flags": null,
  "registry": {"range": "1.1.1.0 - 1.1.1.255", "cidrs": ["1.1.1.0/24"],
               "name": "EXAMPLE-NET", "handle": "1.1.1.0 - 1.1.1.255",
               "type": "ASSIGNED PORTABLE", "rir": "ripe"},
  "errors": {},
  "skipped": {}
}
```

| Key | Type | Meaning |
|---|---|---|
| `reverse` | string or null | PTR name; null = no PTR (not an error) or the DNS lookup failed (`errors.reverse`) |
| `announced` | bool or null | the address is in a BGP-announced prefix; null = RIPEstat failed |
| `prefix` | string or null | the announced prefix (CIDR); null when not announced |
| `asns` | list or null | origin ASNs `{asn: int, holder: string or null}`; `[]` when not announced |
| `rpki` | list or null | `{asn: int, status: string or null}` per origin; null when not announced or RIPEstat failed |
| `abuse_contacts` | list or null | e-mail addresses (only with `--json`) |
| `organization`, `city` | string or null | from ipapi.is |
| `country` | string or null | **with a key the ISO code** (`"AU"`), **keyless the country name** (`"Australia"`); one key, two value forms |
| `flags` | object or null | with a key `{dc, proxy, vpn, tor, mobile, abuser, crawler, anycast}`, each as ipapi.is sends it: a bool (a string if it sends one), null when missing; **keyless always `null`** |
| `registry` | object or null | the RIR-registered range: `range` (`"start - end"`), `cidrs` (list), `name`, `handle`, `type` (string or null), `rir` (`ripe`, `arin`, `apnic`, `lacnic`, `afrinic`, `nic.br`) |
| `errors` | object | source name → message, one entry per failed source |
| `skipped` | object | source name → reason, a source not asked (not a failure) |

Source names (the keys of `errors`/`skipped`, stable): `ripestat`, `rpki`, `abuse`, `rdap`,
`ipapi`, `reverse`. The messages are free text for people (e.g. `"HTTP 503"`, `"HTTP 429:
quota (ipapi.is daily quota used up)"`), never parse them.

- **Keyless quota used up (HTTP 429)**: `organization`, `country`, `city` are null,
  `skipped` is `{"ipapi": "keyless daily quota used up"}`, `errors` stays `{}`. Every later
  address in the same run has the same `skipped` without asking ipapi.is. The exit
  status is unchanged (0 when nothing else failed). With a key, a 429 is
  `errors.ipapi` instead.
- **Failed source**: for example RDAP answering 503 gives `registry: null`,
  `errors: {"rdap": "HTTP 503"}`. The other fields are filled, the reason also goes to
  stderr (`cca: 1.1.1.1: rdap: HTTP 503`), and the **exit status is 1**. A RIPEstat failure
  also leaves `rpki` null without its own entry.
- Exit status of a `--json` run: 1 when any element has a non-empty `errors`, else 0;
  2 for usage or configuration errors (then no JSON is printed).

Pinned by `tests/test_cca_asn.py` (`test_json_output` keyed,
`test_json_contract_keyless_quota_and_failed_source` keyless, quota and failure).

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
