"""CLI entry point for tmux-cli-python.

Provides the Typer-based CLI matching the bash cca-tmux-cli API:
  list, run, read, session, --robot-init, --doctor, --robot-help, --version

Plus new commands: audit query
"""

import builtins
import logging
import sys
from typing import Annotated

import typer

from tmux_cli_python import __version__
from tmux_cli_python.audit import AuditLogger, AuditQuery
from tmux_cli_python.config import AppConfig, derive_session_name, load_config, resolve_agent
from tmux_cli_python.hooks import (
    run_redaction_hooks,
    run_validation_hooks,
)
from tmux_cli_python.tmux_core import (
    TmuxCoreError,
    ensure_session,
    format_window_list,
    session_exists,
)
from tmux_cli_python.tmux_core import (
    create_session as tmux_create_session,
)
from tmux_cli_python.tmux_core import (
    list_windows as tmux_list_windows,
)
from tmux_cli_python.tmux_core import (
    read_output as tmux_read_output,
)
from tmux_cli_python.tmux_core import (
    run_command as tmux_run_command,
)

app = typer.Typer(
    name="tmux-cli-python",
    help="Run commands in visible SSH sessions via tmux, with hook pipeline and audit trail.",
    no_args_is_help=False,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

audit_app = typer.Typer(help="Audit trail operations.")
app.add_typer(audit_app, name="audit")


# ---------------------------------------------------------------------------
# Global state (resolved after argument parsing)
# ---------------------------------------------------------------------------


class State:
    """Mutable state passed through Typer context."""

    server: str = ""
    session: str = ""
    config: AppConfig = AppConfig()
    debug: bool = False


logger = logging.getLogger("tmux_cli_python")


def _setup_debug_logging() -> None:
    """Configure debug-level logging to stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[debug] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def _resolve_config(session_override: str) -> AppConfig:
    """Load config and apply session override / derivation."""
    cfg = load_config()
    if session_override:
        cfg.session.name = session_override
    elif not cfg.session.name:
        cfg.session.name = derive_session_name()
    return cfg


# ---------------------------------------------------------------------------
# Callback — global options parsed before subcommands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="Show version."),
    ] = False,
    robot_init: Annotated[
        bool,
        typer.Option("--robot-init", help="Show configuration template for agents."),
    ] = False,
    doctor: Annotated[
        bool,
        typer.Option("--doctor", help="Validate configuration and show status."),
    ] = False,
    robot_help: Annotated[
        bool,
        typer.Option("--robot-help", help="Show agent-specific documentation."),
    ] = False,
    target_server: Annotated[
        str,
        typer.Option("-t", "--target", help="Target specific server."),
    ] = "",
    session_name: Annotated[
        str,
        typer.Option("-s", "--session", help="Target session name."),
    ] = "",
    debug: Annotated[
        bool,
        typer.Option("-x", "--debug", help="Enable debug mode."),
    ] = False,
) -> None:
    """tmux-cli-python — Run commands in visible SSH sessions via tmux."""
    state = State()
    ctx.ensure_object(dict)
    ctx.obj = state

    state.server = target_server
    state.session = session_name
    state.debug = debug
    state.config = _resolve_config(session_name)

    if debug:
        _setup_debug_logging()
        logger.debug("debug mode enabled")
        logger.debug("config loaded from: %s", state.config.config_path or "(defaults)")
        logger.debug("session name: %s", state.config.session.name or "(not set)")

    if version:
        typer.echo(__version__)
        raise typer.Exit()

    if robot_init:
        logger.debug("robot-init requested")
        _robot_init()
        raise typer.Exit()

    if doctor:
        logger.debug("doctor check requested")
        _doctor(state.config)
        raise typer.Exit()

    if robot_help:
        logger.debug("robot-help requested")
        _robot_help()
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
def list(
    ctx: typer.Context,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="Show raw tmux window listing."),
    ] = False,
) -> None:
    """List active server windows."""
    state: State = ctx.obj
    cfg = state.config
    session_name = cfg.session.name
    agent = resolve_agent(cfg)

    audit = AuditLogger(log_dir=cfg.audit.dir, enabled=cfg.audit.enabled)

    if raw:
        if not session_exists(session_name):
            typer.echo(f"Error: Session '{session_name}' does not exist.", err=True)
            audit.write_now(agent=agent, server=state.server, action="list")
            raise typer.Exit(1)
        session = ensure_session(session_name)
        windows = tmux_list_windows(session, raw=True)
        output = format_window_list(windows, raw=True)
        typer.echo(output)
        typer.echo()
        typer.echo(
            "Note: '-' and '*' are tmux indicators (last/active window), not part of server names"
        )
        audit.write_now(agent=agent, server=state.server, action="list")
        return

    # Default output — just server names
    if session_exists(session_name):
        session = ensure_session(session_name)
        windows = tmux_list_windows(session)
        window_names = format_window_list(windows)
    else:
        window_names = ""

    # Always show available servers from config
    if cfg.session.servers:
        typer.echo(f"Available servers (TMUX_SESSION_SERVERS): {' '.join(cfg.session.servers)}")

    if not window_names:
        typer.echo(f"No active server windows in '{session_name}'.")
        typer.echo('Run a command to start: tmux-cli-python -t <SERVER> run "uptime"')
    else:
        typer.echo("Active windows:")
        typer.echo(window_names)

    audit.write_now(agent=agent, server=state.server, action="list")


@app.command()
def run(
    ctx: typer.Context,
    command: Annotated[str, typer.Argument(help="Command to execute.")],
    interval: Annotated[
        int,
        typer.Option("--interval", help="Polling interval in seconds."),
    ] = 2,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Max timeout in seconds."),
    ] = 300,
) -> None:
    """Execute command on remote server (visible in tmux session)."""
    state: State = ctx.obj
    cfg = state.config
    agent = resolve_agent(cfg)

    if not state.server:
        typer.echo("Error: No server specified. Use -t option.", err=True)
        raise typer.Exit(64)

    logger.debug("run: server=%s session=%s command=%s", state.server, cfg.session.name, command)

    audit = AuditLogger(log_dir=cfg.audit.dir, enabled=cfg.audit.enabled)
    import time as _time

    # --- Validation hooks (pre-exec) ---
    t_validate_start = _time.monotonic()
    validation_result = run_validation_hooks(command, cfg.validation)
    t_validate_ms = int((_time.monotonic() - t_validate_start) * 1000)
    logger.debug(
        "validation completed in %dms: allowed=%s", t_validate_ms, validation_result.allowed
    )
    validation_audit = [
        {"hook": r.hook, "result": r.action, **({"reason": r.reason} if r.reason else {})}
        for r in validation_result.results
    ]

    if not validation_result.allowed:
        typer.echo(f"Validation denied: {validation_result.reason}", err=True)
        audit.write_now(
            agent=agent,
            server=state.server,
            action="run",
            command=command,
            validation=validation_audit,
        )
        raise typer.Exit(1)

    # --- Execute command via tmux ---
    try:
        t0 = _time.monotonic()
        logger.debug("ensuring session: %s", cfg.session.name)
        session = ensure_session(cfg.session.name)
        logger.debug(
            "sending command to server %s (interval=%ds, timeout=%ds)",
            state.server,
            interval,
            timeout,
        )
        result = tmux_run_command(
            session=session,
            server_name=state.server,
            command=command,
            poll_interval=interval,
            timeout=timeout,
        )
        duration_ms = int((_time.monotonic() - t0) * 1000)
        logger.debug(
            "command completed in %dms (exit_code=%d, timed_out=%s)",
            duration_ms,
            result.exit_code,
            result.timed_out,
        )

        if result.timed_out:
            typer.echo(f"ERROR: Command did not complete within timeout of {timeout}s", err=True)
            typer.echo("Current output so far:")
            typer.echo("======================")
            typer.echo(result.output)
            typer.echo("======================")
            typer.echo(
                "Program still running - I cannot run more commands until user stops it "
                "or confirms completion."
            )
            typer.echo(f'Check if finished later: tmux-cli-python read --marker "{result.marker}"')
            audit.write_now(
                agent=agent,
                server=state.server,
                action="run",
                command=command,
                exit_code=124,
                duration_ms=duration_ms,
                validation=validation_audit,
            )
            raise typer.Exit(124)

        # --- Redaction hooks (post-exec) ---
        t_redact_start = _time.monotonic()
        redaction_result = run_redaction_hooks(result.output, cfg.redaction)
        t_redact_ms = int((_time.monotonic() - t_redact_start) * 1000)
        logger.debug(
            "redaction completed in %dms: allowed=%s", t_redact_ms, redaction_result.allowed
        )
        redaction_audit = [
            {"hook": r.hook, "result": r.action, **({"reason": r.reason} if r.reason else {})}
            for r in redaction_result.results
        ]

        if not redaction_result.allowed:
            typer.echo(f"Output blocked: {redaction_result.reason}", err=True)
            audit.write_now(
                agent=agent,
                server=state.server,
                action="run",
                command=command,
                exit_code=result.exit_code,
                duration_ms=duration_ms,
                validation=validation_audit,
                redaction=redaction_audit,
            )
            raise typer.Exit(1)

        # --- Success — show output ---
        typer.echo(redaction_result.output)
        audit.write_now(
            agent=agent,
            server=state.server,
            action="run",
            command=command,
            exit_code=result.exit_code,
            duration_ms=duration_ms,
            validation=validation_audit,
            redaction=redaction_audit,
        )
        raise typer.Exit(result.exit_code)

    except TmuxCoreError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(78)


@app.command()
def read(
    ctx: typer.Context,
    history: Annotated[
        int | None,
        typer.Argument(help="Number of history lines to read."),
    ] = None,
    all_output: Annotated[
        bool,
        typer.Option("--all", help="Read all scrollback history."),
    ] = False,
    marker: Annotated[
        str | None,
        typer.Option("--marker", help="Read output between markers."),
    ] = None,
) -> None:
    """Read screen output from tmux."""
    state: State = ctx.obj
    cfg = state.config
    agent = resolve_agent(cfg)

    if not state.server:
        typer.echo("Error: No server specified. Use -t option.", err=True)
        raise typer.Exit(64)

    audit = AuditLogger(log_dir=cfg.audit.dir, enabled=cfg.audit.enabled)

    try:
        session = ensure_session(cfg.session.name)
        output = tmux_read_output(
            session=session,
            server_name=state.server,
            history=history,
            all_output=all_output,
            marker=marker,
        )
        typer.echo(output)
        audit.write_now(agent=agent, server=state.server, action="read")

    except TmuxCoreError as exc:
        typer.echo(f"Error: {exc}", err=True)
        audit.write_now(agent=agent, server=state.server, action="read", exit_code=78)
        raise typer.Exit(78)


@app.command()
def session(
    ctx: typer.Context,
    servers: Annotated[
        builtins.list[str] | None,
        typer.Argument(help="Server names to connect."),
    ] = None,
) -> None:
    """Create SSH windows for servers in tmux session."""
    state: State = ctx.obj
    cfg = state.config
    agent = resolve_agent(cfg)
    server_list = servers or cfg.session.servers

    if not server_list:
        typer.echo(
            "Error: No servers specified and TMUX_SESSION_SERVERS not defined in config.",
            err=True,
        )
        raise typer.Exit(64)

    audit = AuditLogger(log_dir=cfg.audit.dir, enabled=cfg.audit.enabled)

    try:
        tmux_create_session(
            session_name=cfg.session.name,
            servers=server_list,
        )
        typer.echo(f"Session '{cfg.session.name}' ready with servers: {' '.join(server_list)}")
        audit.write_now(
            agent=agent,
            server=",".join(server_list),
            action="session",
        )

    except TmuxCoreError as exc:
        typer.echo(f"Error: {exc}", err=True)
        audit.write_now(
            agent=agent,
            server=",".join(server_list),
            action="session",
            exit_code=78,
        )
        raise typer.Exit(78)


# ---------------------------------------------------------------------------
# Audit subcommands
# ---------------------------------------------------------------------------


@audit_app.command("query")
def audit_query(
    ctx: typer.Context,
    today: Annotated[bool, typer.Option("--today", help="Show today's audit entries.")] = False,
    server: Annotated[str | None, typer.Option("--server", help="Filter by server.")] = None,
    agent: Annotated[str | None, typer.Option("--agent", help="Filter by agent.")] = None,
    action: Annotated[
        str | None, typer.Option("--action", help="Filter by action (run, read, session, list).")
    ] = None,
    date: Annotated[str | None, typer.Option("--date", help="Filter by date (YYYY-MM-DD).")] = None,
) -> None:
    """Query audit trail entries."""
    state: State = ctx.obj
    log_dir = state.config.audit.dir

    if not state.config.audit.enabled:
        typer.echo("Audit trail is disabled.", err=True)
        raise typer.Exit(1)

    q = AuditQuery(log_dir=log_dir)
    entries = q.query(today=today, server=server, agent=agent, action=action, date=date)

    if not entries:
        typer.echo("No audit entries found.")
        raise typer.Exit()

    import json

    for entry in entries:
        typer.echo(json.dumps(entry, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Agent commands (no subcommand — handled in callback)
# ---------------------------------------------------------------------------


def _robot_init() -> None:
    """Show configuration template for AI agents."""
    typer.echo("=== tmux-cli-python - Configuration Template ===")
    typer.echo()
    typer.echo("YOU MUST CREATE .tmux-cli-python.yaml file:")
    typer.echo()
    typer.echo("STEP 1: Find servers used in this project")
    typer.echo("→ Check project documentation (README.md, CLAUDE.md)")
    typer.echo("→ Check inventory files where servers are defined")
    typer.echo("→ Look for server lists in project configuration")
    typer.echo()
    typer.echo("STEP 2: Create .tmux-cli-python.yaml with this template:")
    typer.echo()
    typer.echo("```yaml")
    typer.echo("session:")
    typer.echo("  name: cca-<PROJECT_NAME>")
    typer.echo('  servers: "server1 server2 server3"')
    typer.echo()
    typer.echo("validation:")
    typer.echo("  enabled: true")
    typer.echo("  hooks:")
    typer.echo('    - "dippy --cmd-stdin --json --remote"')
    typer.echo("  confirmation:")
    typer.echo("    cmd: \"zenity --question --text '{message}' --title 'Confirm command'\"")
    typer.echo()
    typer.echo("redaction:")
    typer.echo("  enabled: true")
    typer.echo("  hooks:")
    typer.echo('    - "secretctl sanitize"')
    typer.echo("  confirmation:")
    typer.echo("    cmd: \"zenity --question --text '{message}' --title 'Sensitive output'\"")
    typer.echo()
    typer.echo("audit:")
    typer.echo("  enabled: true")
    typer.echo("  dir: logs")
    typer.echo()
    typer.echo("logging:")
    typer.echo("  enabled: false")
    typer.echo('  admin_name: ""')
    typer.echo("```")
    typer.echo()
    typer.echo("STEP 3: Test each server:")
    typer.echo('  tmux-cli-python -t <server> run "hostname"')
    typer.echo()
    typer.echo("For detailed help: tmux-cli-python --robot-help")


def _doctor(config: AppConfig) -> None:
    """Validate configuration and show status."""
    exit_code = 0

    typer.echo("=== tmux-cli-python - Status Check ===")
    typer.echo()

    # 1. Config file
    typer.echo("Config file: ", nl=False)
    if config.config_path:
        typer.echo(f"✓ {config.config_path}")
    else:
        typer.echo("✗ None found (run --robot-init)")
        exit_code = 1

    # 2. Session name
    typer.echo("Session name: ", nl=False)
    if config.session.name:
        typer.echo(f"✓ {config.session.name}")
    else:
        derived = derive_session_name()
        typer.echo(f"⚠ Derived: {derived} (save to config file)")

    # 3. Servers
    typer.echo("Servers: ", nl=False)
    if config.session.servers:
        typer.echo(f"✓ {len(config.session.servers)} configured")
        typer.echo(f"  → {' '.join(config.session.servers)}")
    else:
        typer.echo("✗ None configured")
        exit_code = 1

    # 4. Validation hooks
    typer.echo("Validation: ", nl=False)
    if config.validation.enabled:
        typer.echo(f"✓ Enabled ({len(config.validation.hooks)} hook(s))")
    else:
        typer.echo("○ Disabled")

    # 5. Redaction hooks
    typer.echo("Redaction: ", nl=False)
    if config.redaction.enabled:
        typer.echo(f"✓ Enabled ({len(config.redaction.hooks)} hook(s))")
    else:
        typer.echo("○ Disabled")

    # 6. Audit
    typer.echo("Audit: ", nl=False)
    if config.audit.enabled:
        agent_info = f", agent: {resolve_agent(config)}" if resolve_agent(config) else ""
        typer.echo(f"✓ Enabled (dir: {config.audit.dir}{agent_info})")
    else:
        typer.echo("○ Disabled")

    # 7. Logging
    if config.logging.enabled:
        typer.echo("Logging: ", nl=False)
        if config.logging.admin_name:
            typer.echo(f"✓ Enabled (admin_name={config.logging.admin_name})")
        else:
            typer.echo("✗ Enabled but admin_name missing")
            exit_code = 1
    else:
        typer.echo("Logging: ✓ Disabled (default)")

    # 8. Tmux check
    import shutil

    typer.echo("Tmux: ", nl=False)
    if shutil.which("tmux"):
        typer.echo("✓ Installed")
    else:
        typer.echo("✗ Not found")
        exit_code = 1

    typer.echo()
    status = "OK" if exit_code == 0 else "ISSUES FOUND"
    typer.echo(f"=== Status: {status} ===")
    raise typer.Exit(exit_code)


def _robot_help() -> None:
    """Show agent-specific documentation."""
    typer.echo(
        """# tmux-cli-python - Agent Guide

## What This Tool Does

tmux-cli-python runs commands on remote servers through tmux SSH windows,
with validation hooks (pre-exec), redaction hooks (post-exec), and audit trail.

**IMPORTANT:** Sessions are VISIBLE to users:
- Users can see the command output in their terminal
- Users can interrupt commands with Ctrl-C
- This is for INTERACTIVE use, not background automation

## Agent Setup Workflow

### Step 1: Check Configuration
```bash
tmux-cli-python --robot-init
```

### Step 2: Create Configuration File

Create `.tmux-cli-python.yaml` (or backward-compat `.cca-tmux-cli`):

```yaml
session:
  name: cca-projectname
  servers: "server1 server2 server3"

validation:
  enabled: true
  hooks:
    - "dippy --cmd-stdin --json --remote"

redaction:
  enabled: true
  hooks:
    - "secretctl sanitize"

audit:
  enabled: true
  dir: logs
```

### Step 3: Verify
```bash
tmux-cli-python --doctor
```

## Common Commands

```bash
# List available servers
tmux-cli-python list

# Run command on server (visible to user)
tmux-cli-python -t server1 run "uptime"

# Read current screen output
tmux-cli-python -t server1 read

# Create SSH session
tmux-cli-python session server1 server2
```

## Hook Pipeline

Commands flow through configurable hooks:

1. **Validation hooks** (pre-exec): receive command string via stdin
   - exit 0 = approve, exit 1 = deny, exit 2 = ask user

2. **Redaction hooks** (post-exec): receive output via stdin, emit redacted via stdout
   - exit 0 = pass, exit 1 = block, exit 2 = ask user

## Troubleshooting

**"No session specified"**
- Add session.name to config file
- Or use `-s` option: `tmux-cli-python -s mysession list`

**"Server not found"**
- Check server is in session.servers config
- Use correct server name with `-t`
"""
    )
