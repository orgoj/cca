# cca netdata

Reads the Netdata API of a server: metric overview, aggregated values, top N, network
latency and packet loss from the fping plugin.

```
cca netdata [--server NAME | --host H [--port P]] [--transport ssh|direct] COMMAND ...
```

- `--server NAME` uses `[servers.NAME]` from `.cca.toml` (`netdata_host`,
  `netdata_port`, `netdata_transport`, `ssh`). Transport `ssh` (default) runs `curl` on
  the server, so no VPN is needed; `direct` sends HTTP from this machine.
- Without `--server`: `--host` (default `localhost`) and `--port` (default 19999),
  direct only. Connection options go before or after COMMAND.
- Times (`--after`, `--before`, UTC): `-SECONDS`, `HH:MM`, `"today HH[:MM]"`,
  `"yesterday HH[:MM]"`, `YYYY-MM-DD`, `"YYYY-MM-DD HH:MM[:SS]"`. Values starting with
  `-` work as `--after -3600`.

| Command | Use it to |
|---|---|
| `list [--pattern S]` | see metric groups, or charts whose id contains S |
| `meta --context C` | see charts, dimensions and labels of a context |
| `discover "QUESTION"` | get context suggestions for a question |
| `stats --context C` | see values per interval (`--aggregation`, `--points` 1-1000, `--instance`, `--dimension`) |
| `top --context C` | rank labels (domains first); `--group-by instance` for `app.*` |
| `query --context C` | get the raw `v3/data` JSON |
| `fping` | latency over all targets plus packet loss (default last 15 min) |
| `fping --per-target` | find which targets are slow |
| `fping --history [--target T]` | event trend over 90 days, cached in `netdata.fping_cache_dir`; `--refresh` fetches again |
| `fping --all [--history]` | one line per `[servers]` entry, each over its own transport |

- `--target` defaults to `netdata.fping_target`; without it `--history` needs `--target`.
- Pull `--history` from a lightly loaded server; a cached series is reused until
  `--refresh`.
- Exit 1: the API could not be read (message names the URL); `fping --all` reports such
  servers as unreachable and still exits 0. Exit 2: usage or configuration error.

Example: `cca netdata --server server1 stats --context system.load --after -86400`
