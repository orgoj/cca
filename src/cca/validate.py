"""Value rules shared by the config and secrets schemas (doc-2 "General rules", "HTTPS URLs")."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
NAME_MAX = 64
# ssh destination [user@]host; never starts with "-" (doc-2 servers.<name>.ssh)
SSH_TARGET_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9._-]*@)?[A-Za-z0-9][A-Za-z0-9._-]*")
# netdata.fping_target and `cca netdata fping --target` (doc-2 [netdata]), max NAME_MAX
FPING_TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_LABEL_RE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?")


def has_control(value: str) -> bool:
    return _CONTROL_RE.search(value) is not None


def display(value: str) -> str:
    """A name or key safe to print: non-printable characters escaped."""
    return value if value.isprintable() else value.encode("unicode_escape").decode("ascii")


def clean(value: Any) -> Any:
    """API JSON with every string made safe for the terminal (control characters escaped)."""
    if isinstance(value, str):
        return display(value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {display(k): clean(v) for k, v in value.items()}
    return value


def is_name(value: str) -> bool:
    return len(value) <= NAME_MAX and NAME_RE.fullmatch(value) is not None


def dns_name(value: str) -> str | None:
    """Normalized DNS name (one terminal dot removed, lowercased), or None if invalid."""
    name = value[:-1] if value.endswith(".") else value
    if not 1 <= len(name) <= 253:
        return None
    if not all(len(label) <= 63 and _LABEL_RE.fullmatch(label) for label in name.split(".")):
        return None
    return name.lower()


def host(value: str) -> str | None:
    """Normalized host: IPv4, bare IPv6 or DNS name; None if invalid."""
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return dns_name(value)


def parse_https_url(url: str) -> tuple[tuple[str, str, int], str]:
    """Split an HTTPS URL into its normalized origin and the rest (path, query, fragment).

    Raises ValueError with a reason that never repeats the URL.
    """
    if has_control(url) or "\\" in url or any(c.isspace() for c in url):
        raise ValueError("contains whitespace, a control character or a backslash")
    scheme, sep, rest = url.partition("://")
    if not sep or scheme.lower() != "https":
        raise ValueError("scheme must be https")
    end = len(rest)
    for c in "/?#":
        i = rest.find(c)
        if i != -1:
            end = min(end, i)
    authority, tail = rest[:end], rest[end:]
    if "@" in authority:
        raise ValueError("userinfo is not allowed")
    port_text = None
    if authority.startswith("["):
        close = authority.find("]")
        if close == -1:
            raise ValueError("unterminated IPv6 literal")
        try:
            name = ipaddress.IPv6Address(authority[1:close]).compressed
        except ValueError:
            raise ValueError("invalid IPv6 literal") from None
        after = authority[close + 1 :]
        if after:
            if not after.startswith(":"):
                raise ValueError("invalid authority")
            port_text = after[1:]
    else:
        hostname, colon, port_part = authority.partition(":")
        if colon:
            port_text = port_part
        if not hostname:
            raise ValueError("host is empty")
        try:
            name = ipaddress.IPv4Address(hostname).compressed
        except ValueError:
            normalized = dns_name(hostname)
            if normalized is None:
                raise ValueError("invalid host") from None
            name = normalized
    port = 443
    if port_text is not None:
        if not port_text.isascii() or not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise ValueError("port must be 1-65535")
        port = int(port_text)
    return ("https", name, port), tail
