# Operations: problems, unknown servers, logs, safety

Commands come from [run](run.md), [server](server.md), [netdata](netdata.md) and
[hetrix](hetrix.md); written results follow [knowledge](knowledge.md) and
[records](records.md). Project specifics (log pipelines, timezones, bot rules, reload
scripts, critical servers) are in the project guides, never guessed.

## Safety

- **Ask before** destructive or service-impacting commands: `rm -rf`, `kill -9`,
  `DROP`/`DELETE`, `systemctl stop|restart`, `docker stop`, `reboot`, `shutdown`, and every
  change on a server the project marks critical. A fix or any other change is a proposal
  until the user approves it; read-only diagnostics need no approval unless a project
  guide says otherwise.
- **Secrets stay out of output.** Inspect configs, env files, process arguments and app
  settings for the required non-secret fields only (`grep -E '^(listen|server_name) '`,
  `systemctl show -p FragmentPath,User,Group,WorkingDirectory UNIT`; never the
  `Environment` or `ExecStart` properties, which can carry credentials); never print
  passwords, tokens, keys, cookies or connection strings, and never `cat` a whole env or
  credentials file. If a needed value may be secret, show its presence or length, not its
  content (`grep -c '^DB_PASSWORD=' .env`).
- **Config files of a running service** may be reloaded by automation at any time: follow
  the project guide before editing. A service usually reads every file in its config
  directory, so never leave `.bak`/`.orig` copies there; keep copies outside it. Test and
  apply with the project's procedure from its guide, not a reload command known from
  elsewhere.
- **One command per server at a time.** `cca run --read` is only for recovering an earlier
  run that timed out, was interrupted or lost its marker; never a check before a new
  command.
- **sudo password prompts** appear only over the tmux transport, in the visible window:
  the user types the password there. If the run timed out meanwhile, do not repeat it:
  `cca run --read --marker M SERVER` gives its output and status. After the user says
  "retry" following authorization, repeat the exact same approved command. Over ssh there
  is no terminal for a prompt: use a command that needs none or ask.
- Permanent changes go through the project's configuration management (as its guides
  say); `cca run` is for diagnostics and approved one-off fixes.
- Bot, crawler and rate-limit rules are project-specific: find them in the guides before
  proposing any block.

Working economy: never repeat a listing or search whose result is already in the
conversation; do only the narrow action asked; JSON in shell goes through `yq`; several
items = one tool run with several arguments; when a tool lacks an output you need, extend
the tool instead of a throwaway parser.

## Solving a server problem

1. **Guides first, before touching the server:** `tantivy2agents search "<2-4 words>"`
   for each area involved (nginx, cache, bots ... separately), plus
   `tantivy2agents search "<symptom> incident" --limit 5`. Read every relevant result and
   follow it; projects often forbid automatic log downloads or have a log/outage playbook.
2. **Server context:** the server guide (`guides/servers/<name>.md`, found by
   `tantivy2agents search "<server>"`).
3. **Verify the real files** the guides point to (configs, scripts) before relying on
   them; a guide states intent, not necessarily today's state.
4. **Diagnose** with data, local log data first (the project log guide):
   `cca server status SERVER` (load, memory, disks),
   `cca netdata --server SERVER top --context C` / `stats --context C` for metrics,
   `cca hetrix status` / `cca hetrix outages` for
   external monitoring, `cca run -t SERVER -- CMD` for targeted checks. Compare with
   matching past incidents by concrete overlap (same service, symptom, server).
5. **Plan the change:** name the files to change and the dependencies whose current
   content you verified; no side map of unrelated references. Get approval.
6. **Test the result functionally** after any live change: the behaviour and the error
   logs, a real check, not a re-read of your own reasoning.
7. **Document:** an incident (and a guide when the procedure is reusable), per
   [records](records.md).

## Unknown server: discover, never assume

No assumption about the stack (nginx, Apache, Docker ...) or the host type; never cut
system command output with `head`/`tail`. Without a server guide, this is the start.

1. **Identity and inventory:** `cca server info SERVER` (OS, CPU, memory, disks, ZFS,
   interfaces, Docker/Swarm/LXC/QEMU) and `cca server status SERVER`.
2. **Host type:** `cca run -t SERVER -- ps -o comm= -p 1` (the init's name, no
   arguments): `systemd` = VM, bare metal or LXC with systemd; `my_init` with `runsv`
   processes = baseimage container; `lxc` in mounts or hostname = LXC.
3. **Full process tree without arguments** (arguments can carry passwords, tokens and
   connection strings, and would reach the output and the tmux window):
   `cca run -t SERVER -- ps ax -o pid,ppid,user,comm --forest`; read all of it: PID 1,
   supervisors, web servers, databases, application processes. When one argument of a
   process is needed (e.g. its config path), first identify the executable, then select
   only that known non-secret argument by the executable's documented syntax and whole
   argument boundaries, on the server; when you are not sure the value is non-secret,
   report only whether it is present. Never `ps aux`/`ps axuf` or a raw
   `/proc/PID/cmdline`. Saving output: only the project's gitignored `tmp/`.
4. **Listeners:** `cca run -t SERVER -- ss -tlnp` (older systems: `netstat -tlnp`);
   `0.0.0.0:443` exposed, `127.0.0.1:N` local backend, an exposed database port is a
   finding.
5. **Stack details, only for what step 3 showed:** `nginx -T 2>/dev/null | grep -E 'server_name|listen'`,
   `apache2ctl -S`, `docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'`,
   `systemctl list-units --type=service --state=running`, the app server's config file
   (non-secret fields only).
6. **Data and logs:** `df -h`, the data directories the configs name, `ls /var/log/`; an
   application's log files from its config or `ls -l /proc/PID/fd | grep -i log`, never a
   `find /` sweep.
7. **Write the server guide** `guides/servers/<name>.md` ([records](records.md)). Record
   hostnames, topology and providers only in the project, never in shared tools.

## Logs

1. **The project log guide first:** `tantivy2agents search "log analysis"`,
   `tantivy2agents search "<server> logs"`. Its scripts, paths, queries and timezone tables
   define the procedure; without a guide, ask the user.
2. Local copy or database before reading live on the server; do not start a project's
   fetch/import pipeline on your own (data is usually there; refresh only when asked, data
   is missing or the incident is fresh).
3. The project's analysis scripts for aggregates (how many, where, who) before ad-hoc
   queries; their output is never cut. Tracing **one known entity** (URL, request id, IP)
   at a known time: search its lines directly in the log.
4. Never assume format or timezone: per-server differences (UTC vs local, field names) are
   common, and a wrong conversion is a wrong conclusion.
5. On the server read targeted (`grep -c`, `grep PATTERN FILE | tail -n 10`), never a
   `tail -n 100` of random lines; during a live incident do not grep server logs when a
   local copy exists.
6. Check rotation and retention before declaring data missing; a fresh request may not be
   flushed yet.
7. Exports and intermediate results go to the project's `tmp/`, never the system `/tmp`.
8. A claim about where a request went or what the backend did needs a query in the right
   log layer (proxy view is not backend reality); otherwise say `unverified`.
