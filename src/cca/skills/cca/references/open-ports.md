# cca open-ports

Probes TCP ports of a host and shows the raw output of the probe tool.

```
cca open-ports [-d SERVER] [-k] [-m nmap|nc|curl] [-n] HOST [PORT...]
```

- HOST: DNS name, IPv4 or IPv6 (without brackets). PORTs replace the default list
  `20 22 25 80 443`; `-k` adds the Kubernetes ports instead. Put options before or after
  all ports, not between them.
- `-m nmap` (default) runs one `nmap -Pn --reason -p ...` call; its exit code is the
  result (closed ports do not fail it). `-m nc` and `-m curl` probe each port, every
  port is probed, exit 1 when any probe failed; `curl` prints `HOST:PORT ok` or
  `HOST:PORT failed (curl exit N)` per port.
- `-d SERVER` runs the probes on a server from `[servers]` in `.cca.toml` over ssh
  (only then is a `.cca.toml` needed); the tool must exist on that server.
- `-n` prints the commands without running anything.
- Exit 2: usage error, unknown server, missing tool (named), or ssh failure.

Example: `cca open-ports -d server1 -m nc 203.0.113.10 22 443`
