---
name: cca-server-discovery
description: "Use when investigating an unknown server to systematically discover services and stack without assumptions."
allowed-tools: Bash(*), Read(*), Glob(*), Grep(*)
---

# Server Discovery - Careful Unknown Server Investigation

**PREREQUISITE:** Load `cca-core` for system overview and safety rules.

**Purpose:** Systematically discover what runs on an unknown server WITHOUT assumptions. Never guess the tech stack - discover it step by step.

## GOLDEN RULE: NO ASSUMPTIONS!

- **NEVER assume** Apache, nginx, Docker, or any specific technology
- **NEVER use head/tail** on system commands (they have short output)
- **Server types vary**: LXC containers, Docker containers, bare metal, VMs - discover which one it is
- **If no guide exists** for a server, THIS skill is the starting point

## cca-tmux-cli hostname rules

- Některé servery vyžadují **plné hostname** (FQDN): `cca-tmux-cli -t server1.example.com run "..."`
- Pokud `cca-tmux-cli -t server run` vrací "Failed to create window", zkus FQDN
- Ověř dostupné servery: `cca-tmux-cli list`

## Step 1: Basic Identity

```bash
# WHO is this server? (run ALL, no head/tail!)
cca-tmux-cli -t SERVER run "hostname && cat /etc/os-release"
cca-tmux-cli -t SERVER run "uptime && free -h"
cca-tmux-cli -t SERVER run "ip addr show | grep 'inet '"
cca-tmux-cli -t SERVER run "df -h"
```

**Determine container type from clues:**
- `/sbin/my_init` + `runsv` = **Phusion baseimage Docker container**
- `systemd` as PID 1 = **VM, bare metal, or LXC with systemd**
- `lxc` in hostname or mount paths = **LXC container**
- Check: `cca-tmux-cli -t SERVER run "cat /proc/1/cmdline | tr '\x00' ' '"`

## Step 2: Full Process Tree

```bash
# FULL process tree - read ALL of it, don't skip anything
cca-tmux-cli -t SERVER run "ps axuf"
# Saving it? Only into the PROJECT's gitignored tmp/ (tmp/SERVER-ps.txt),
# never into the shared system /tmp.
```

**What to look for in process tree:**
- PID 1 tells you the init system (my_init, systemd, init)
- Service supervisors (runsv, supervisord, systemd)
- Web servers (nginx, apache2, uwsgi, gunicorn, node)
- Databases (mysql, postgres, redis, mongo)
- Application processes (python, java, php-fpm, node)

## Step 3: Network Listeners

```bash
# What ports are open? Try both commands (ss may not exist on old systems)
cca-tmux-cli -t SERVER run "ss -tlnp"
# If ss not found:
cca-tmux-cli -t SERVER run "netstat -tlnp"
```

**Analyze listeners:**
- `0.0.0.0:80` or `0.0.0.0:443` = web server exposed
- `127.0.0.1:XXXXX` = local-only services (uwsgi workers, app backends)
- `0.0.0.0:3306` = MySQL exposed (check if intentional!)
- `0.0.0.0:8088` = alternative HTTP port

## Step 4: Web/App Stack Details

**ONLY after you know what's running from ps output!**

For **uwsgi emperor** (pattern: `--emperor /path/*/werkzeug*.ini`):
```bash
# List all managed apps
cca-tmux-cli -t SERVER run "ls /home/*/www/*/werkzeug*.ini"
# Check specific app config
cca-tmux-cli -t SERVER run "cat /home/*/www/APPNAME/werkzeug.ini"
```

For **nginx**:
```bash
cca-tmux-cli -t SERVER run "nginx -T 2>/dev/null | grep server_name"
```

For **apache2**:
```bash
cca-tmux-cli -t SERVER run "apache2ctl -S 2>/dev/null"
```

For **Docker host**:
```bash
cca-tmux-cli -t SERVER run "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

For **systemd services**:
```bash
cca-tmux-cli -t SERVER run "systemctl list-units --type=service --state=running"
```

## Step 5: Disk and Data Layout

```bash
cca-tmux-cli -t SERVER run "df -h"
cca-tmux-cli -t SERVER run "ls -la /var/www/ /home/*/www/ /opt/ /data/ 2>/dev/null"
```

## Step 6: Logs Location

```bash
# Find log locations based on what you discovered
cca-tmux-cli -t SERVER run "ls /var/log/"
# App logs: ask the process, don't sweep the filesystem. `find /home` or `find /` over a large
# tree is forbidden - the paths are in the app config you already read (Step 4), or here:
cca-tmux-cli -t SERVER run "ls -l /proc/<PID>/fd | grep -i log"
```

## Step 7: Create Server Guide

After discovery, ALWAYS create a guide:
```
cca/guides/servers/{servername}.md
```

Include:
- Server type (Docker container / LXC / bare metal / VM)
- OS version
- Hardware specs (CPU, RAM, disk)
- IP addresses
- Running services with versions
- Application list
- Key file paths
- Known issues

## Recording Discovered Server Patterns

Do not copy infrastructure examples from a project into this shared skill. Record discovered
hostnames, topology, providers, roles, service counts, and storage details only in that project's
own documentation.

---

*This skill prevents embarrassing assumptions about server technology. Always discover, never guess!*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
