---
name: cca-core
description: CCA (Claude Code Admin) Core - MANDATORY entry point for ANY work on servers. Read this before running any command on any server. Covers cca-tmux-cli syntax, git workflow for server files, safety rules, and core workflows.
allowed-tools: Bash(*), Read(*), Glob(*), Grep(*)
---

# CCA Core System

**CRITICAL: Load this skill IMMEDIATELY whenever you are about to do anything on servers — commands, edits, diagnostics, anything.**

CCA is a universal system for server management, incident resolution, and knowledge management.

## Architecture & Tools

### 1. Investigation: `cca-tmux-cli`
Used for real-time diagnostics and troubleshooting via persistent tmux sessions.
- `cca-tmux-cli list` - List available servers
- `cca-tmux-cli -t <SERVER> run "<COMMAND>"` - Execute command, returns output directly
- `cca-tmux-cli -t <SERVER> read` - Recover terminal state after an earlier ambiguous/unfinished `run`

**⚠️ CRITICAL SYNTAX RULES:**
- `-t` MUST come BEFORE the subcommand: `cca-tmux-cli -t server1 run "..."` ✅
- `run` returns output directly — do NOT read tmux screen after it
- **Do not run `read` proactively before a command.** The next command's type is irrelevant.
- Use `read` only after an earlier `run` timed out, was interrupted, lost its final marker, or otherwise
  left it unclear whether the shared terminal is still busy. Read the screen before issuing another `run`.
- If output contains only `[sudo] password for ...:`, the command did NOT run. Never interpret empty
  output after such a run as success.
- When the user says "retry" after completing sudo authorization, immediately repeat the EXACT same
  approved command. Do not investigate guides, permissions, or alternative approaches in between.
- **Interactive terminal serialization:** `cca-tmux-cli` targets a persistent interactive tmux terminal. Never send a second command to the same target while a previous `run` is still running or its final output and exit code are not known. After a timeout, do not start another `run`; first use `read` to determine whether the previous command is still running. Only issue the next command after the previous one is confirmed finished.

#### Multi-line `run` with `cat <<'EOF'`
```bash
cca-tmux-cli -t server1 run "$(cat <<'EOF'
cd /opt/app/repo
git pull --ff-only
EOF
)"
```
```bash
cca-tmux-cli -t server1 run "$(cat <<'EOF'
if [ -d /opt/app/repo ]; then
  docker ps --format '{{.Names}} {{.Status}}' | grep myapp
else
  echo "missing /opt/app/repo"
fi
EOF
)"
```
```bash
cca-tmux-cli -t server1 run "$(cat <<'EOF'
python3 - <<'PY'
print("ok")
PY
EOF
)"
```

### Git Workflow for Server Files

Some server files (e.g. a proxy config repo under `/opt/...`) are git-versioned **on the server itself**.
Which paths, and how changes get applied (test/reload scripts), is defined in the PROJECT guides —
always look it up there first. **MANDATORY** — edit + diff must happen in ONE command:

```bash
# 1. Before edit: check state
cca-tmux-cli -t server1 run "cd /opt/app/config-repo && git status && git diff --stat"
# If dirty → stop, resolve first (foreign uncommitted change!)

# 2. Edit + immediate diff in ONE command
cca-tmux-cli -t server1 run "$(cat <<'EOF'
python3 -c "
import re
with open('conf/example.conf') as f: content = f.read()
# ... edit ...
with open('conf/example.conf', 'w') as f: f.write(content)
" && cd /opt/app/config-repo && git diff
EOF
)"

# 3. After diff approved: apply per PROJECT guide (test/reload script = LIVE CHANGE,
#    needs its own explicit user approval!), then commit
cca-tmux-cli -t server1 run "cd /opt/app/config-repo && ./test-reload.sh && git add conf/example.conf && git commit -m 'description'"
```

### 2. Configuration: `ap` (Ansible Playbooks)
Used for permanent changes and infrastructure configuration.
- `ap <PLAYBOOK> [-l <SERVER>]` - Run ansible playbook

### 3. Knowledge: `tantivy2agents`
Full-text search across guides, incidents, and documentation.
- `tantivy2agents search "<KEYWORDS>"` - Search knowledge base

## Core Workflow

1.  **Analyze**: Understand the problem.
2.  **Search**: `tantivy2agents search` for guides in `cca/guides/`.
3.  **Investigate**: Use `cca-tmux-cli` to check server state.
4.  **Fix**: Use `ap` for permanent fixes or `cca-tmux-cli` for troubleshooting.
5.  **Document**: Save findings as guides in `cca/guides/`.

## Decision Matrix

| Task | Tool | Example |
|------|------|---------|
| Check if server is alive | `cca-tmux-cli` | `cca-tmux-cli -t server1 run "uptime"` |
| Install software | project deployment tool | Follow the project's deployment guide |
| Check service status | `cca-tmux-cli` | `cca-tmux-cli -t server1 run "systemctl status nginx"` |
| View logs | `cca-tmux-cli` | `cca-tmux-cli -t server1 run "tail -20 /var/log/syslog"` |

## Log Analysis Rules

**NIKDY neděj tail -100 na log a nečti náhodné řádky!**

1. **Zjisti formát** - `tail -5 /var/log/service.log` (max 5 řádků)
2. **Spočítej chyby** - `grep -c 'ERROR\|500\|Traceback' logfile`
3. **Zobraz jen chyby** - `grep 'ERROR\|500' logfile | tail -10`
4. **Časové rozložení** - `grep 'ERROR' logfile | grep -oP 'timestamp_pattern' | uniq -c`

**Proč:** Random tail plýtvá kontextem normálními requesty. Cílený grep najde problém okamžitě.

## nginx Rules

- **sites-enabled**: nginx parsuje VŠECHNY soubory v tomto adresáři - NIKDY tam vytvářet .bak!
- **Zálohy**: vždy do `/tmp/`, nikdy do sites-enabled/
- **Test před reload**: `nginx -t && nginx -s reload`

## Safety Rules

### ⛔ NIKDY git stash/reset/checkout na serverech s live configs!

Git-verzovane konfigurace na serverech (typicky config repo proxy/webserveru v `/opt/...`) jsou zive soubory:
reload muze probehnout kdykoliv (cron reload skripty, rucni zasah admina), takze zmena obsahu na disku
= potencialni zmena zive konfigurace. `git stash` / `git reset --hard` / `git checkout <file>` meni
obsah bez kontroly = **RIZIKO VYPADKU**.

**POZOR: nepredpokladej NIC o tom, kdy se zmena aplikuje.** U nekterych nastroju spousti reload
automatika (cron, ban/blacklist skripty) i bez tebe, v nahodny okamzik a casto **bez testu syntaxe**;
u jinych se neaplikuje nic, dokud reload nespustis sam. Rozhoduje VYHRADNE projektovy guide
daneho nastroje — over ho (viz Guide-First nize). Bez ohledu na nastroj plati:

- **"Necommitnute" NEZNAMENA "neni zive".** Rozpracovana zmena lezici v config adresari muze byt
  uz aktivni — cizi necommitnutou zmenu ber jako potencialne bezici produkcni konfiguraci.
- **Vlastni zmenu aplikuj vedome** (test + reload skript dle guide) — nespolehej na to, ze ji za tebe
  nasadi cizi automatika. Ta ji nasadi neotestovanou a v cas, ktery neurcujes.

- ✅ Bezpecne: `git add`, `git commit`, `git diff`, `git log`, `git status`
- ❌ ZAKAZANO: `git stash`, `git reset`, `git checkout <file>`, `git restore`

### NEVER run dangerous commands without explicit approval!
- **Destructive**: `rm -rf`, `kill -9`, `DROP/DELETE` in DB
- **Service impacts**: `systemctl stop`, `docker stop`, `reboot`, `shutdown`
- **Critical servers**: Require manual approval for ALL changes (see configuration)

## Assistant Operational & Token-Saving Rules

### 1. Zero Redundancy & Token-Saving
- **NEVER repeat listing or information commands** (like `ls`, `git status`, or duplicate searches) if the data is already present in your active conversation history.
- **NEVER run Git status or Git diff** in general analytical or chat turns unless explicitly requested by the user, or when performing a final commit.
- **Laser Focus on User Request**: If the user asks for a specific, narrow action (e.g. "write the change to the incident report"), do ONLY that. Do NOT run additional diagnostic queries, logs analysis, or background scans unless requested.

### 2. Guide-First & Tool Discipline
- **MANDATORY Guide Lookup**: Before using any custom wrapper or system tool (like `asn-wrap`), ALWAYS search the guides first with `tantivy2agents` to find the exact usage instructions. Never guess command parameters.
- **Use Custom Tools Directly**: Use the designated tools (`asn-wrap`, `tantivy2agents`, etc.) exactly as described. Do not try to bypass them or run alternative commands unless the wrapper is verified to fail.
- **NEVER hand-parse tool output with ad-hoc `python3 -c` / `python3 - <<PY`.** Ad-hoc python is the LAST resort, only when no other path exists — never the first reach.
  - If a tool lacks the output format you need, **EXTEND THE TOOL** (add a `-s`/`--short` flag) instead of wrapping it in a throwaway script. The one-off dies with the session; the flag serves every future one.
  - **JSON in bash = `jq`**, not python. Several items = ONE tool run with multiple arguments, not a `for` loop around the wrapper.
  - Example: `asn-wrap -s IP [IP...]` prints one compact line per IP (org, ASN, CC, dc/proxy/mobile, reputation, reverse). Without `-s` it returns full JSON for fields the short form omits.

### 3. Traffic Analysis & Rate-Limiting Accuracy
- Bot/crawler handling rules (which bots to allow, what URLs may be blocked, rate-limit patterns)
  are PROJECT-specific — always find them via `tantivy2agents search` in the project guides
  before proposing any blocking. Never invent blocking rules from general knowledge.

---
*Note: This skill is universal. Project configuration (servers, inventory) is handled automatically via .cca-env (legacy .env) or servers.json. Use `cca-doctor` to verify your environment.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
