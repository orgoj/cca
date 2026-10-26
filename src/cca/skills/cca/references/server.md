# cca server

Facts about a server from `[servers]`: is it the right host, how is it doing, what runs
on it.

```
cca server {hostname,status,info} [--timeout SEC] (SERVER | --all)
```

- `hostname`: the server's hostname; a quick check that ssh works and you reach the
  host you mean.
- `status`: quick state: local and server time (clock skew), load, memory, ext/xfs
  usage, ZFS pools.
- `info`: inventory: OS, CPU, memory size, disks, ZFS layout, network interfaces
  (prefixes from `server_info.net_iface_prefixes`, default `en`, `eth`), loopback
  aliases, Docker containers, Swarm services, LXC containers, QEMU processes.

Always over ssh, never in a tmux window (`run.transport` is only for `cca run`); one ssh
call per section, each in the `[run.log]` command log.

Output, one tag per section:

```
<server-status server="server1">
<admin-time>2026-10-15T17:00:00+02:00</admin-time>
<server-time>2026-10-15T17:00:01+02:00</server-time>
<load> 17:00:01 up 3 days,  load average: 0.10, 0.20, 0.30</load>
<memory>
...
</memory>
<storage>...</storage>
<zfs>ZFS not available</zfs>
</server-status>
```

A missing tool prints `... not available` (not a failure). A section whose command fails
gets `exit="N"` (`exit="timeout"`) on its tag; the other sections still run.

`--timeout SEC` is the total time for one server (default 120). `--all` runs every
server in config order and stops at the first non-zero exit.

Exit 0 all sections ran; 124 timeout; 255 ssh failed (no further calls to that
server); 125 a section's output passed 16 MiB (ssh killed, the section tag gets
`exit="output-limit"` and its first 64 KiB, the report stops, `--all` too); 2 usage or configuration error.

For anything else on the server use `cca run`.
