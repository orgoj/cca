# cca ioc

Read the host-ioc compromise check of the project's hosts. host-ioc (script, cron, mail
alerts, its config) is deployed by the project's Ansible role and runs as root on each
host; `cca ioc` only reads its state. Nothing is written on a host.

```
cca ioc [--timeout SEC] status [HOST...]
cca ioc [--timeout SEC] show HOST [ID]
cca ioc [--timeout SEC] baseline HOST
```

- `status`: per host and run (`quick`, `deep`): start time and age, duration, version,
  findings (new). WARN when a run is missing or unreadable, older than 2x its interval,
  has modules not `ok`/`finding` (uncovered), or its `script_sha256` differs from the
  local `ioc.script` (the version the role deploys). A `last-error.txt` newer than a
  run's start (host-ioc aborted, its state was not rewritten) is a WARN line with the
  last traceback line; read the file with `cca run`.
- `show HOST`: the findings of both last runs. `show HOST ID`: every field of that
  finding, then raw data to verify it, read-only: for `pid` the process from `/proc`
  (exe, cwd, cmdline, status, cgroup, children), for `path` `ls -ld` and the lines around
  `line` (without `line`: the last lines of a `php_logs` log, else the first lines; binary
  files only their sha256). A container file is `/proc/<init PID>/root/...`: after a
  container restart it is reported `unavailable` with the path inside the container
  (read it there with `cca run`, or wait for the next run). The listing also shows the
  reasons of uncovered modules. Verify a finding here before you act on it; act only
  through the normal change process.
- `baseline HOST`: runs `host-ioc baseline` on HOST and saves its proposal to
  `ioc.baseline_dir/<host>+<UTC time>.yaml`. Review it and put the accepted parts into
  the host's Ansible vars; the baseline is never changed on the host.

Config (`.cca.toml`, doc-2 `[ioc]`):

```toml
[ioc]
hosts = ["server1", "server2"]   # [servers] entries running host-ioc
script = "ansible/roles/host-ioc/files/host-ioc"   # local copy the role deploys
transport = "ssh"                # or "run": the run.transport of `cca run`
sudo = false                     # true: read through `sudo -n`
quick_interval_hours = 24
deep_interval_hours = 24
baseline_dir = "tmp/host-ioc"
```

Every remote call is in the `[run.log]` command log as `ioc status|show|baseline`.
Values from a host are untrusted: shown escaped, `pid`/`path` validated before use.

Exit 0 nothing to report; 1 findings; 2 a warning, a host error (status goes on with the
next host), usage or config error.
