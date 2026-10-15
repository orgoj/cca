---
name: cca
description: The `cca` command (Cyber-CLI Admin) for server administration in a project with a .cca.toml. Use before running any `cca` subcommand, when setting up or checking a project's .cca.toml, or when installing skills with `cca install skills`.
---

# cca

One command, `cca <subcommand>`. Project settings come only from the nearest `.cca.toml`
(found from the current directory upwards); secrets only from the project's sops files.
`cca --help` and `cca <subcommand> --help` are authoritative; this skill says when to use
what.

| Subcommand | Use it to | Reference |
|---|---|---|
| `cca asn` | look up IP addresses: ASN, RPKI, organization, country, datacenter/proxy/VPN flags, PTR | [asn](references/asn.md) |
| `cca check-domain` | check whether a domain points to our hosting: DNS, address owner, hosting marker, redirects | [check-domain](references/check-domain.md) |
| `cca cloudflare` | read and change Cloudflare zones: DNS, WAF rules, audit, events, traffic, exports | [cloudflare](references/cloudflare.md) |
| `cca config show` | see which `.cca.toml` is used and its values with defaults | [config](references/config.md) |
| `cca curl` | call an HTTP API with a project credential you never see | [curl](references/curl.md) |
| `cca doctor` | check that the project is ready for cca | [doctor](references/doctor.md) |
| `cca hetrix` | check HetrixTools monitors: UP/DOWN, outages, response times, server agent stats, blacklists | [hetrix](references/hetrix.md) |
| `cca install skills` | link the shipped skills into an agent skill directory | [install](references/install.md) |
| `cca netdata` | read Netdata metrics of a server: load, top N, network latency and packet loss | [netdata](references/netdata.md) |
| `cca open-ports` | check which TCP ports of a host are reachable, locally or from a server | [open-ports](references/open-ports.md) |
| `cca watchlist` | run the daily check over Backlog.md: due and recurring tasks, notes valid on a date | [watchlist](references/watchlist.md) |

Rules:

- Run `cca` from the project directory (or below it); never pass secrets on the command line.
- Exit code 2 means a usage or configuration error; the message names the file and key.
- `cca --version` prints the installed release.
