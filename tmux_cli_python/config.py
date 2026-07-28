"""Configuration loader for tmux-cli-python.

Supports these config sources (priority order):
1. .tmux-cli-python.yaml — native YAML config with hooks, audit, etc.
2. .cca-tmux-cli — backward-compatible bash env file
3. .cca-env — CCA project config (avoids collisions with other tools using .env)
4. .env — general environment (legacy fallback)

Both are searched recursively from cwd up to /.

Environment variable fallback: CCA_AGENT is checked if no config agent is set.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Config schema (dataclasses — no pydantic dependency needed)
# ---------------------------------------------------------------------------


@dataclass
class SessionConfig:
    """Tmux session configuration."""

    name: str = ""
    servers: list[str] = field(default_factory=list)


@dataclass
class ConfirmationConfig:
    """Confirmation command config for hook exit-code 2 (ask user)."""

    cmd: str = ""

    def format_message(self, message: str) -> str:
        """Return the confirmation command with {message} replaced."""
        return self.cmd.replace("{message}", message)


@dataclass
class HookPipelineConfig:
    """Configuration for a hook pipeline (validation or redaction)."""

    enabled: bool = False
    hooks: list[str] = field(default_factory=list)
    confirmation: ConfirmationConfig = field(default_factory=ConfirmationConfig)


@dataclass
class AuditConfig:
    """Audit trail configuration."""

    enabled: bool = True
    dir: str = "logs"
    agent: str = ""


@dataclass
class LoggingConfig:
    """Legacy logging configuration (backward compat with bash)."""

    enabled: bool = False
    admin_name: str = ""


@dataclass
class AppConfig:
    """Top-level application configuration."""

    session: SessionConfig = field(default_factory=SessionConfig)
    validation: HookPipelineConfig = field(default_factory=HookPipelineConfig)
    redaction: HookPipelineConfig = field(default_factory=HookPipelineConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    config_path: str | None = None  # Path to the loaded config file


# ---------------------------------------------------------------------------
# Agent name resolution
# ---------------------------------------------------------------------------


def resolve_agent(config: AppConfig) -> str:
    """Resolve the agent name from config, falling back to CCA_AGENT env var.

    Priority:
    1. config.audit.agent (from YAML or bash env file)
    2. CCA_AGENT environment variable
    3. Empty string
    """
    return config.audit.agent or os.environ.get("CCA_AGENT", "")


# ---------------------------------------------------------------------------
# YAML config loader
# ---------------------------------------------------------------------------

DEFAULT_YAML_FILENAME = ".tmux-cli-python.yaml"


def _parse_session(raw: dict) -> SessionConfig:
    servers_raw = raw.get("servers", "")
    if isinstance(servers_raw, str):
        servers = shlex.split(servers_raw)
    elif isinstance(servers_raw, list):
        servers = [str(s) for s in servers_raw]
    else:
        servers = []
    return SessionConfig(name=raw.get("name", ""), servers=servers)


def _parse_confirmation(raw: dict | None) -> ConfirmationConfig:
    if raw is None:
        return ConfirmationConfig()
    return ConfirmationConfig(cmd=raw.get("cmd", ""))


def _parse_hook_pipeline(raw: dict | None) -> HookPipelineConfig:
    if raw is None:
        return HookPipelineConfig()
    return HookPipelineConfig(
        enabled=raw.get("enabled", False),
        hooks=raw.get("hooks", []),
        confirmation=_parse_confirmation(raw.get("confirmation")),
    )


def _parse_audit(raw: dict | None) -> AuditConfig:
    if raw is None:
        return AuditConfig()
    return AuditConfig(
        enabled=raw.get("enabled", True),
        dir=raw.get("dir", "logs"),
        agent=raw.get("agent", ""),
    )


def _parse_logging(raw: dict | None) -> LoggingConfig:
    if raw is None:
        return LoggingConfig()
    return LoggingConfig(
        enabled=raw.get("enabled", False),
        admin_name=raw.get("admin_name", ""),
    )


def load_yaml_config(path: Path) -> AppConfig:
    """Load configuration from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig(
        session=_parse_session(raw.get("session", {})),
        validation=_parse_hook_pipeline(raw.get("validation")),
        redaction=_parse_hook_pipeline(raw.get("redaction")),
        audit=_parse_audit(raw.get("audit")),
        logging=_parse_logging(raw.get("logging")),
        config_path=str(path),
    )


# ---------------------------------------------------------------------------
# Bash env config loader (.cca-tmux-cli, .cca-env, .env)
# ---------------------------------------------------------------------------

BASH_ENV_FILENAME = ".cca-tmux-cli"
CCA_ENV_FILENAME = ".cca-env"
GENERAL_ENV_FILENAME = ".env"

# Regex to parse KEY=VALUE lines from bash env files.
# Handles: KEY=value, KEY="value", KEY='value', export KEY=value
_ENV_LINE_RE = re.compile(
    r"""^\s*(?:export\s+)?        # optional 'export '
    (?P<key>[A-Za-z_][A-Za-z0-9_]*)  # variable name
    \s*=\s*                          # equals sign
    (?P<quote>["']?)                 # optional opening quote
    (?P<value>.*?)                   # value
    (?P=quote)?                      # matching closing quote
    \s*$""",
    re.VERBOSE,
)


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a bash env file into a dict. Ignores comments and blank lines."""
    result: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            m = _ENV_LINE_RE.match(line)
            if m:
                result[m.group("key")] = m.group("value")
    return result


def load_bash_env_config(path: Path) -> AppConfig:
    """Load configuration from a bash env file (.cca-tmux-cli, .cca-env or .env)."""
    env = _parse_env_file(path)

    servers_raw = env.get("TMUX_SESSION_SERVERS", "")
    servers = shlex.split(servers_raw) if servers_raw else []

    return AppConfig(
        session=SessionConfig(
            name=env.get("TMUX_SESSION_NAME", ""),
            servers=servers,
        ),
        logging=LoggingConfig(
            enabled=env.get("CCA_LOGGING", "false").lower() == "true",
            admin_name=env.get("ADMIN_NAME", ""),
        ),
        audit=AuditConfig(
            agent=env.get("CCA_AGENT", ""),
        ),
        config_path=str(path),
    )


# ---------------------------------------------------------------------------
# Recursive config search (mimics bash behavior: search cwd up to /)
# ---------------------------------------------------------------------------


def _find_config_recursive(filename: str, start_dir: Path | None = None) -> Path | None:
    """Search for a file from start_dir (default: cwd) up to /."""
    current = start_dir or Path.cwd()
    current = current.resolve()

    while True:
        candidate = current / filename
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break  # reached root
        current = parent
    return None


def load_config(start_dir: Path | None = None) -> AppConfig:
    """Load configuration with priority: YAML > bash env > cca env > general env.

    Search order (recursive from start_dir to /):
    1. .tmux-cli-python.yaml — full native config
    2. .cca-tmux-cli — bash compat config (higher priority)
    3. .cca-env — CCA project config (avoids .env collisions)
    4. .env — general environment (lowest priority, legacy fallback)
    """
    # Priority 1: YAML config
    yaml_path = _find_config_recursive(DEFAULT_YAML_FILENAME, start_dir)
    if yaml_path is not None:
        return load_yaml_config(yaml_path)

    # Priority 2-4: bash env files
    # Mimic bash behavior: .cca-tmux-cli wins over .cca-env, which wins over .env
    # A lower-priority file doesn't stop the search — keep looking higher up
    for filename in (BASH_ENV_FILENAME, CCA_ENV_FILENAME, GENERAL_ENV_FILENAME):
        path = _find_config_recursive(filename, start_dir)
        if path is not None:
            return load_bash_env_config(path)

    # No config found — return defaults
    return AppConfig()


def derive_session_name(directory: Path | None = None) -> str:
    """Derive session name from directory name (same logic as bash).

    - Strip common prefixes (ansible-, infra-)
    - Add cca- prefix
    """
    d = directory or Path.cwd()
    name = d.name
    for prefix in ("ansible-", "infra-"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return f"cca-{name}"
