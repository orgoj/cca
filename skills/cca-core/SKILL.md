---
name: cca-core
description: CCA (Cyber-CLI Admin) Core - MANDATORY entry point for ANY work on servers. Read this before running any command on any server. Covers cca-tmux-cli syntax, git workflow for server files, safety rules, and core workflows.
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
- `cca-tmux-cli -t <SERVER> run --script <<'REMOTE'` - Execute a literal multiline Bash script from stdin
- `cca-tmux-cli -t <SERVER> read` - Recover terminal state after an earlier ambiguous/unfinished `run`

**⚠️ CRITICAL SYNTAX RULES:**
- `-t` MUST come BEFORE the subcommand: `cca-tmux-cli -t server1 run "..."` ✅
- `run` returns output directly — do NOT read tmux screen after it
- If the immediate output contains only `[sudo] password for ...:`, the state is ambiguous, not a
  harness failure: use `cca-tmux-cli -t SERVER read`. If the preserved output contains a final
  `EXITCODE=0` marker and the user confirms entering the password, the command completed normally.
  Do not stop and do not repeat it; verify its effect read-only and continue. An active prompt
  without a final marker means the command is still unfinished.
- When the user says "retry" after completing sudo authorization, immediately repeat the EXACT same
  approved command. Do not investigate guides, permissions, or alternative approaches in between.
- **One command per target at a time, and `read` only to recover an ambiguous earlier `run`** —
  full rule in the `cca-tmux-cli` skill (*When to use `read`*).

#### Multiline `run --script`

Use a directly attached heredoc with a quoted delimiter. This is the only supported multiline form;
the quoted delimiter prevents local shell expansion of the script contents.

```bash
cca-tmux-cli -t server1 run --script <<'REMOTE'
cd /opt/app/repo
git pull --ff-only
REMOTE
```
```bash
cca-tmux-cli -t server1 run --script <<'REMOTE'
if [ -d /opt/app/repo ]; then
  docker ps --format '{{.Names}} {{.Status}}' | grep myapp
else
  echo "missing /opt/app/repo"
fi
REMOTE
```
```bash
cca-tmux-cli -t server1 run --script <<'REMOTE'
python3 - <<'PY'
print("ok")
PY
REMOTE
```

### Git Workflow for Server Files

Some server files (e.g. a proxy config repo under `/opt/...`) are git-versioned **on the server itself**.
Which paths, and how changes get applied (test/reload scripts), is defined in the PROJECT guides —
always look it up there first. **MANDATORY** — edit + diff must happen in ONE command:

```bash
# 1. Before edit: check state
cca-tmux-cli -t server1 run "cd /opt/app/config-repo && git status && git diff --stat"
# If dirty → stop, resolve first (foreign uncommitted change!)

# 2. Edit + immediate diff in ONE command. Use a targeted, reviewable edit (a single `sed`
#    substitution, or `git apply` of a patch) — never a script that rewrites the whole file,
#    which hides what changed. If the same repo is also checked out locally, edit it there
#    with the harness's file-editing tool and deploy per the project guide instead.
cca-tmux-cli -t server1 run "cd /opt/app/config-repo && sed -i 's/^worker_processes 4;/worker_processes 8;/' conf/example.conf && git diff"

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

## Log Analysis

**Never `tail -100` a log and read random lines** — targeted counting and filtering finds the problem,
random tail just burns context on normal traffic. Procedure, per-project formats, timezones and tools:
**`cca-server-logs` skill** (its first step is finding the project's log guide).

## Config Files of a Running Service

- A service usually parses **every** file in its config directory — never leave `.bak`/`.orig` there.
  Keep copies outside the directory the service reads.
- **How a config is tested and applied is defined by the project guide for that tool**, not by
  general knowledge of the daemon. Do not substitute a reload command you know from elsewhere for the
  project's test/reload script.

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
- **NEVER run Git status or Git diff** in general analytical or chat turns unless explicitly requested
  by the user, when performing a final commit, or in the server-config workflow above (there the
  before-edit `git status` and the after-edit `git diff` are mandatory — they catch a foreign
  uncommitted change on a live config).
- **Laser Focus on User Request**: If the user asks for a specific, narrow action (e.g. "write the change to the incident report"), do ONLY that. Do NOT run additional diagnostic queries, logs analysis, or background scans unless requested.

### 2. Guide-First & Tool Discipline
- **MANDATORY Guide Lookup**: Before using any custom wrapper or system tool (like `asn-wrap`), ALWAYS search the guides first with `tantivy2agents` to find the exact usage instructions. Never guess command parameters.
- **Use Custom Tools Directly**: Use the designated tools (`asn-wrap`, `tantivy2agents`, etc.) exactly as described. Do not try to bypass them or run alternative commands unless the wrapper is verified to fail.
- **NEVER hand-parse tool output with ad-hoc `python3 -c` / `python3 - <<PY`.** Ad-hoc python is the LAST resort, only when no other path exists — never the first reach.
  - If a tool lacks the output format you need, **EXTEND THE TOOL** (add a `-s`/`--short` flag) instead of wrapping it in a throwaway script. The one-off dies with the session; the flag serves every future one.
  - **JSON in bash = `jq`**, not python. Several items = ONE tool run with multiple arguments, not a `for` loop around the wrapper.
  - Example: `asn-wrap -s IP [IP...]` prints one compact line per IP (org, ASN, CC, dc/proxy/mobile, reputation, reverse). Without `-s` it returns full JSON for fields the short form omits.

### 3. Written Knowledge: Evidence & Length (guides, incidents, reports)

**The single source for this rule.** It covers every written artifact — guides, incidents, TODO
entries, research output, reports in chat — and it is not restated anywhere else; other skills point
here. A guide or incident is a durable record that people and agents act on for years, so a
plausible-sounding sentence nobody checked is worse than a missing one.

**Only verified information.**
- Write what you **observed** (command output, log line, file content, user statement) — not what
  you concluded it probably means. Keep the two apart in the text.
- Every number, timestamp, version, path, hostname and limit must come from a command you actually
  ran or a file you actually read. **Never estimate, never reconstruct from memory, never round a
  number you did not measure.**
- No invented metrics: no "confidence 85 %", no "match 95 %", no severity score — you have no
  mechanism computing them. State the concrete overlap instead ("same service, same symptom").
- **Unverified belongs in the text only when it is labelled and actionable:** mark it
  `neovereno`/`unverified` **and add how to verify it** (the exact command or query). An unlabelled
  guess becomes a fact for the next reader.
- Anything already marked `neovereno` / `assumed` / `probably` in an existing guide is a **task to
  verify, not a fact to build on**. Verifying is usually cheaper than the consequences.
- Do not paraphrase someone else's statement into your own interpretation. Record what they said;
  mark what you inferred as your inference.
- Contradicting an existing entry needs evidence, not a new opinion. `Read` the current text first;
  do not overwrite a decision someone made because your partial finding points elsewhere.

**Short and factual.**
- Length follows content: cover the substance, then stop. No filler sections, no restating the same
  thing in an intro and a summary, no boilerplate headings kept empty "for completeness".
- Drop a template section that has nothing verified to put in it — an empty or speculative
  `Root Cause` is worse than no section.
- Each command, path and rule appears **once**, in the place it belongs. Moving content elsewhere
  leaves a link (`→ path/to/guide.md`), never a shortened copy.
- Prose that explains what the command already shows is noise. Show the command and its real output.
- No dated changelog inside a guide — history is in git. The guide reads as current as a whole.

### 4. Traffic Analysis & Rate-Limiting Accuracy
- Bot/crawler handling rules (which bots to allow, what URLs may be blocked, rate-limit patterns)
  are PROJECT-specific — always find them via `tantivy2agents search` in the project guides
  before proposing any blocking. Never invent blocking rules from general knowledge.

---
*Note: This skill is universal. Project configuration (servers, inventory) is handled automatically via .cca-env (legacy .env) or servers.json. Use `cca-doctor` to verify your environment.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
