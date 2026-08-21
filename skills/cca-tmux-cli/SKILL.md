---
name: cca-tmux-cli
description: "Run commands in visible SSH sessions via tmux. Agent-friendly CLI for server management."
---

# CCA Tmux CLI

**Purpose:** Execute commands on remote servers through tmux SSH windows. Sessions are VISIBLE to users - they can see output and interrupt commands.

## Key Concept

This tool wraps `tmux` and `ssh` to run bash commands on remote machines while maintaining persistent, visible sessions that users can attach to and monitor.

**IMPORTANT:** This is NOT for background/hidden automation. Users can see command output and interrupt with Ctrl-C.

## Agent Workflow

Always start by checking configuration:

```bash
# 1. Check if project is configured
cca-tmux-cli --robot-init

# 2. If configured, validate setup
cca-tmux-cli --doctor

# 3. If NOT configured, read setup guide
cca-tmux-cli --robot-help
```

## Main Commands

| Command | Description |
|---------|-------------|
| `cca-tmux-cli list` | List active server windows |
| `cca-tmux-cli -t <server> run "<cmd>"` | Execute command (visible in tmux) |
| `cca-tmux-cli -t <server> read` | Recover state after an ambiguous/unfinished earlier `run` |
| `cca-tmux-cli session <srv1> <srv2>` | Create SSH windows for servers |

## Agent-Specific Commands

| Command | Purpose |
|---------|---------|
| `--robot-init` | Check if project configured (WARNING if not) |
| `--doctor` | Validate configuration and show status |
| `--robot-help` | Detailed agent setup documentation |

## Configuration

Required environment variables (in the project's `.cca-env`; legacy `.env` is still read as fallback):

```bash
TMUX_SESSION_NAME=cca-projectname
TMUX_SESSION_SERVERS="server1 server2 server3"
CCA_LOGGING=false
# CCA_LOGGING=true
# ADMIN_NAME=agent  # Required only if CCA_LOGGING=true
```

## Troubleshooting

### When to use `read`

`read` is not a preparatory check and must not be run proactively before a new command. Use it only
when an earlier `run` timed out, was interrupted, did not return its final marker, or otherwise left
the shared tmux terminal in an unknown state. Inspect the screen to determine whether that earlier
command is still running; issue the next `run` only after the terminal is confirmed idle.

Whether the next command is read-only, diagnostic, interactive, or mutating does not affect this rule.

**"No session specified"**
- Add `TMUX_SESSION_NAME` to config file
- Or use `-s` option: `cca-tmux-cli -s mysession list`

**"Server not found"**
- Check server is in `TMUX_SESSION_SERVERS`
- Use correct server name with `-t`

**"Configuration error"**
- Run `cca-tmux-cli --doctor`
- Check all required variables are set

## Examples

```bash
# Check configuration first
cca-tmux-cli --robot-init

# List available servers
cca-tmux-cli list

# Run command (visible to user)
cca-tmux-cli -t server1 run "uptime"

# Read output from screen
cca-tmux-cli -t server1 read

# Create new SSH session
cca-tmux-cli session server1 server2
```

For detailed setup: `cca-tmux-cli --robot-help`


<!-- SHARED SKILL: Keep project-agnostic. For project-specific extensions, create a local skill. -->
