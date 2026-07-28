---
name: cca-analyzing-logs
description: Analyze log file and suggest new read-only patterns for auto-approval
allowed-tools: Read(*), Bash(*), Edit(*)
---

# Analyze Log Permissions

Analyze log files to identify read-only commands that could be auto-approved.

## Steps

### 1. Analysis
**Find log file to analyze:**
   - If `$ARGUMENTS` provided: use that log file path
   - If no arguments: find and use the most recent log in `logs/` directory
   - Use bash command: `ls -1t logs/*.log | head -1` to find latest

**Extract server commands:**
   - Read the log file
   - Extract all lines containing `cca-tmux-cli ... run "..."` commands
   - Parse the inner commands (the part in quotes after `run`)

### 2. Execution
**Identify read-only commands:**
   - For each extracted command, determine if it's read-only
   - Read-only commands include:
     - System info: uptime, free, df, date, hostname, uname
     - Apache status: apache2ctl fullstatus/status
     - File viewing: ls, cat, head, tail, less, more, wc
     - Search: grep, zgrep, find
     - Log analysis: lnav with SELECT queries
   - Dangerous commands to EXCLUDE:
     - File modifications: `>>`, `>`, sed -i, echo >
     - Process control: kill, systemctl, service
     - Script execution: .sh files
     - File operations: rm, mv, cp (to system locations)

**Check existing patterns:**
   - Read current allowed patterns from `.claude/danger/allow-server.txt` and `.claude/danger/allow-bash.txt`
   - If not present, use plugin defaults from `${CLAUDE_PLUGIN_ROOT}/danger/allow-server.txt` and `allow-bash.txt`
   - Compare extracted commands with existing patterns
   - Identify which commands are NOT yet covered

### 3. Verification
**Generate suggestions:**
   - Create regex patterns for new read-only commands found
   - Group similar commands (e.g., all grep variations)
   - Format as regex patterns matching the style in allow-server.txt and allow-bash.txt
   - Suggest creating `.claude/danger/allow-{server|bash}.add.txt` files to extend plugin defaults
   - Present to user for approval with:
     - Command example from log
     - Proposed regex pattern
     - Explanation why it's safe

---

*Run after working session with many server commands to capture new safe patterns.*


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
