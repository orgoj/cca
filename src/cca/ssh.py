"""The one place that builds ssh calls: argv only, target from [servers] or validated."""

from __future__ import annotations

from cca import validate
from cca.config import Config
from cca.output import CcaError


def target(cfg: Config, server: str) -> str:
    """The ssh destination of a configured server."""
    return check_target(cfg.server(server)["ssh"])


def check_target(value: str) -> str:
    if not validate.SSH_TARGET_RE.fullmatch(value):
        raise CcaError(f"invalid ssh target '{validate.display(value)}' (expected [user@]host)")
    return value


def argv(destination: str, remote_command: str) -> list[str]:
    """ssh argv: `--`, the validated destination and the remote command.

    The remote command is one element; ssh hands it to the remote shell as is. Options
    belong in the user's ssh config; a caller that needs one gets a named parameter
    here, never a free-form list.
    """
    return ["ssh", "--", check_target(destination), remote_command]
