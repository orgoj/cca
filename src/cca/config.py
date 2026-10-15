"""`.cca.toml` discovery and load-time validation (doc-1 "Config", doc-2)."""

from __future__ import annotations

import ipaddress
import os
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cca import validate
from cca.output import CcaError, warn

FILENAME = ".cca.toml"
SCHEMA_VERSION = 1

_SESSION_RE = re.compile(r"[A-Za-z0-9_-]+")
_OPERATOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_IFACE_RE = re.compile(r"[A-Za-z0-9]+")
_MARKER_RE = re.compile(r"[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*")

REQUIRED = object()  # key must be present
ABSENT = object()  # no default: omitted from the document when not set


class _InvalidError(Exception):
    """A value violates its rule; the loader adds file and dotted key."""


# --- value checks: return the (possibly normalized) value or raise _InvalidError


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise _InvalidError("must be a string")
    if not value:
        raise _InvalidError("must not be empty")
    if validate.has_control(value):
        raise _InvalidError("must not contain control characters")
    return value


def _matching(pattern: re.Pattern[str], max_len: int | None = None) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        value = _string(value)
        if (max_len is not None and len(value) > max_len) or not pattern.fullmatch(value):
            raise _InvalidError(
                f"must match {pattern.pattern}" + (f" (max {max_len})" if max_len else "")
            )
        return value

    return check


def _choice(*choices: str) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        if _string(value) not in choices:
            raise _InvalidError("must be one of " + ", ".join(f'"{c}"' for c in choices))
        return value

    return check


def _integer(low: int, high: int) -> Callable[[Any], int]:
    def check(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise _InvalidError("must be an integer")
        if not low <= value <= high:
            raise _InvalidError(f"must be {low}-{high}")
        return value

    return check


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _InvalidError("must be a boolean")
    return value


def _path(value: Any) -> str:
    value = _string(value)
    if value.startswith("~"):
        raise _InvalidError("must not start with ~ (no home expansion)")
    return value


def _string_list(item: Callable[[Any], Any], non_empty: bool = False) -> Callable[[Any], list]:
    def check(value: Any) -> list:
        if not isinstance(value, list):
            raise _InvalidError("must be an array")
        if non_empty and not value:
            raise _InvalidError("must not be empty")
        for i, element in enumerate(value):
            try:
                item(element)
            except _InvalidError as e:
                raise _InvalidError(f"item {i}: {e}") from None
        return list(value)

    return check


def _host(value: Any) -> str:
    if validate.host(_string(value)) is None:
        raise _InvalidError("must be a hostname, IPv4 or IPv6 address")
    return value


def _ip(value: Any) -> str:
    try:
        ipaddress.ip_address(_string(value))
    except ValueError:
        raise _InvalidError("must be an IPv4 or IPv6 address") from None
    return value


def _hosting_marker(value: Any) -> str:
    rest = _string(value).removeprefix("/")
    if not _MARKER_RE.fullmatch(rest) or any(s in (".", "..") for s in rest.split("/")):
        raise _InvalidError("must be a URL path without . or .. segments")
    return value


def _api_base(value: Any) -> str:
    try:
        _origin, tail = validate.parse_https_url(_string(value))
    except ValueError as e:
        raise _InvalidError(f"must be an HTTPS URL: {e}") from None
    if "?" in tail or "#" in tail:
        raise _InvalidError("must be an HTTPS URL without query or fragment")
    return value


# --- schema: table -> {key: (default, check)}; nested dicts are sub-tables

SERVER: dict[str, tuple[Any, Callable[[Any], Any]]] = {
    "ssh": (ABSENT, _matching(validate.SSH_TARGET_RE)),  # default filled with the server name
    "netdata_host": (ABSENT, _host),
    "netdata_port": (19999, _integer(1, 65535)),
    "netdata_transport": ("ssh", _choice("ssh", "direct")),
}

SCHEMA: dict[str, Any] = {
    "run": {
        "transport": ("tmux", _choice("tmux", "ssh")),
        "tmux": {
            "session": (ABSENT, _matching(_SESSION_RE)),
            "tokf": (False, _boolean),
        },
        # present table = logging on; filled in only when present
        "log": {
            "dir": ("logs", _path),
            "operator": (REQUIRED, _matching(_OPERATOR_RE, validate.NAME_MAX)),
        },
    },
    "secrets": {
        "curl": ("secrets/curl.secret.yaml", _path),
        "cloudflare": ("secrets/cloudflare.secret.yaml", _path),
    },
    "netdata": {
        "fping_cache_dir": ("server-logs/fping", _path),
        "fping_target": (ABSENT, _matching(validate.FPING_TARGET_RE, validate.NAME_MAX)),
    },
    "cloudflare": {
        "export_dir": ("tmp/cloudflare", _path),
        "api_base": ("https://api.cloudflare.com/client/v4", _api_base),
    },
    "check_domain": {
        "our_ips": ([], _string_list(_ip)),
        "hosting_marker": (ABSENT, _hosting_marker),
    },
    "server_info": {
        "net_iface_prefixes": (["en", "eth"], _string_list(_matching(_IFACE_RE), non_empty=True)),
    },
    "diagnose": {
        "apache_status_cmd": ("apache2ctl", _string),
        "mongodb_status_cmd": (ABSENT, _string),
    },
    "watchlist": {
        "file": (ABSENT, _path),  # default chosen by _watchlist_default
    },
}
OPTIONAL_TABLES = {"run.log"}


@dataclass
class Config:
    path: Path  # the loaded .cca.toml
    data: dict[str, Any]  # validated document with defaults filled in

    @property
    def dir(self) -> Path:
        return self.path.parent

    def resolve(self, value: str) -> Path:
        """A path value from the file, resolved from the config dir."""
        return self.dir / value

    def get(self, dotted: str) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        """Use-time validation: a key the calling command needs."""
        value = self.get(dotted)
        if value is None:
            raise CcaError(f"{self.path}: {dotted}: required by this command but not set")
        return value

    def server(self, name: str) -> dict[str, Any]:
        servers = self.data["servers"]
        if name not in servers:
            known = ", ".join(servers) or "none"
            raise CcaError(
                f"{self.path}: unknown server '{validate.display(name)}' (servers: {known})"
            )
        return servers[name]


def find(start: str | None = None) -> Path | None:
    """Nearest .cca.toml from the physical CWD up to / (exclusive)."""
    current = start if start is not None else os.getcwd()
    while True:
        parent = os.path.dirname(current)
        if parent == current:  # reached /
            return None
        candidate = os.path.join(current, FILENAME)
        if os.path.lexists(candidate):  # broken link or directory still stops the walk
            return Path(candidate)
        current = parent


def load(config_arg: str | None = None, start: str | None = None) -> Config | None:
    """Load --config PATH, or the discovered file; None when nothing is found."""
    if config_arg is not None:
        path = Path(os.path.abspath(config_arg))
    else:
        path = find(start)
        if path is None:
            return None
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise CcaError(f"{path}: syntax error: {e}") from None
    except OSError as e:
        raise CcaError(f"{path}: cannot read: {e.strerror}") from None
    return Config(path, _validate(raw, path))


def require(config_arg: str | None = None) -> Config:
    config = load(config_arg)
    if config is None:
        raise CcaError(f"no {FILENAME} found from {os.getcwd()} up to / (use --config PATH)")
    return config


def _fail(path: Path, key: str, reason: str) -> CcaError:
    return CcaError(f"{path}: {validate.display(key)}: {reason}")


def _validate(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    if "schema_version" not in raw:
        raise _fail(path, "schema_version", "required")
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise _fail(path, "schema_version", "must be an integer")
    if version > SCHEMA_VERSION:
        raise _fail(
            path,
            "schema_version",
            f"{version} is newer than the highest version this cca supports ({SCHEMA_VERSION})",
        )
    if version < 1:
        raise _fail(path, "schema_version", "must be at least 1")

    data: dict[str, Any] = {
        "schema_version": version,
        "servers": _servers(raw.get("servers"), path),
    }
    for key in raw:
        if key not in SCHEMA and key not in ("schema_version", "servers"):
            warn(f"unknown key '{validate.display(key)}' in {path}")
    data.update(_table(raw, SCHEMA, "", path))
    data["watchlist"].setdefault("file", _watchlist_default(path.parent))
    return data


def _watchlist_default(config_dir: Path) -> str:
    """doc-2 [watchlist]: first existing file, else by whether cca/ exists."""
    for candidate in ("cca/watchlist.json", "watchlist.json"):
        if (config_dir / candidate).exists():
            return candidate
    return "cca/watchlist.json" if (config_dir / "cca").is_dir() else "watchlist.json"


def _servers(raw: Any, path: Path) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _fail(path, "servers", "must be a table")
    servers: dict[str, Any] = {}
    seen: set[str] = set()
    for name, table in raw.items():
        key = f"servers.{name}"
        if not validate.is_name(name):
            raise _fail(path, key, "server name must match [A-Za-z0-9][A-Za-z0-9_-]* (max 64)")
        if name.lower() in seen:
            raise _fail(path, key, "duplicate server name (names are case-insensitive)")
        seen.add(name.lower())
        if not isinstance(table, dict):
            raise _fail(path, key, "must be a table")
        server = _table(table, SERVER, key + ".", path)
        servers[name] = {"ssh": server.pop("ssh", name), **server}
    return servers


def _table(raw: dict[str, Any], schema: dict[str, Any], prefix: str, path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in raw:
        if key not in schema and prefix:
            warn(f"unknown key '{validate.display(prefix + key)}' in {path}")
    for key, spec in schema.items():
        dotted = prefix + key
        if isinstance(spec, dict):
            sub = raw.get(key)
            if sub is None and dotted in OPTIONAL_TABLES:
                continue
            if sub is None:
                sub = {}
            if not isinstance(sub, dict):
                raise _fail(path, dotted, "must be a table")
            out[key] = _table(sub, spec, dotted + ".", path)
            continue
        default, check = spec
        if key not in raw:
            if default is REQUIRED:
                raise _fail(path, dotted, "required")
            if default is not ABSENT:
                out[key] = list(default) if isinstance(default, list) else default
            continue
        try:
            out[key] = check(raw[key])
        except _InvalidError as e:
            raise _fail(path, dotted, str(e)) from None
    return out
