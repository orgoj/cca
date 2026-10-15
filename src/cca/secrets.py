"""Project secrets from sops files (doc-1 "Secrets", doc-2 "Secrets file shapes").

Decrypted values never reach CCA output: sops output is captured and only parsed,
errors name the file and the key path, never a value, and secret fields are left out
of repr().
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cca import validate
from cca.config import Config
from cca.output import CcaError, warn

_CRED_ID_RE = re.compile(r"[a-z0-9][a-z0-9_]*")

Origin = tuple[str, str, int]


@dataclass(frozen=True)
class Credential:
    id: str
    origins: tuple[Origin, ...]
    csrf: bool = False
    bearer: str | None = field(default=None, repr=False)
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)


def decrypt(path: Path) -> dict[str, Any]:
    """`sops -d --output-type json FILE` as a dict; exit 2 naming what is missing."""
    path = Path(os.path.abspath(path))  # absolute: the argument never starts with "-"
    sops = shutil.which("sops")
    if sops is None:
        raise CcaError(f"sops not found on PATH (needed to decrypt {path})")
    if not path.is_file():
        raise CcaError(f"secrets file not found: {path}")
    # stdout holds plaintext and stderr may too: both are captured and never shown
    try:
        proc = subprocess.run(
            [sops, "-d", "--output-type", "json", str(path)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    except OSError as e:
        raise CcaError(f"cannot decrypt {path}: cannot run {sops}: {e.strerror}") from None
    if proc.returncode != 0:
        raise CcaError(f"cannot decrypt {path}: sops exited with status {proc.returncode}")
    try:
        document = json.loads(proc.stdout)
    except ValueError:
        document = None
    if not isinstance(document, dict):
        raise CcaError(f"cannot decrypt {path}: sops did not return a JSON object")
    return document


def _fail(path: Path, key: str, reason: str) -> CcaError:
    return CcaError(f"{path}: {validate.display(key)}: {reason}")


def _warn_unknown(document: dict[str, Any], known: set[str], prefix: str, path: Path) -> None:
    for key in document:
        if key not in known:
            warn(f"unknown key '{validate.display(prefix + key)}' in {path}")


def _secret_string(value: Any, path: Path, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(path, key, "must be a non-empty string")
    if validate.has_control(value):
        raise _fail(path, key, "must not contain control characters")
    return value


def validate_curl(document: dict[str, Any], path: Path) -> dict[str, Credential]:
    _warn_unknown(document, {"credentials"}, "", path)
    creds = document.get("credentials")
    if not isinstance(creds, dict) or not creds:
        raise _fail(path, "credentials", "must be a map with at least one credential")
    result: dict[str, Credential] = {}
    for cred_id, entry in creds.items():
        key = f"credentials.{cred_id}"
        if not _CRED_ID_RE.fullmatch(cred_id):
            raise _fail(path, key, "credential id must match [a-z0-9][a-z0-9_]*")
        if not isinstance(entry, dict):
            raise _fail(path, key, "must be a map")
        _warn_unknown(entry, {"origins", "bearer", "username", "password", "csrf"}, key + ".", path)
        origins = entry.get("origins")
        if not isinstance(origins, list) or not origins:
            raise _fail(path, f"{key}.origins", "must be a non-empty array")
        parsed: list[Origin] = []
        for i, url in enumerate(origins):
            okey = f"{key}.origins[{i}]"
            if not isinstance(url, str):
                raise _fail(path, okey, "must be a string")
            try:
                origin, tail = validate.parse_https_url(url)
            except ValueError as e:
                raise _fail(path, okey, f"must be https://HOST[:PORT]: {e}") from None
            if tail not in ("", "/"):
                raise _fail(path, okey, "must be https://HOST[:PORT] without path or query")
            if origin in parsed:
                raise _fail(path, okey, "duplicate origin after normalization")
            parsed.append(origin)
        has_bearer = "bearer" in entry
        has_basic = "username" in entry or "password" in entry
        if has_bearer == has_basic:
            raise _fail(path, key, "needs exactly one of bearer or username + password")
        values = {
            name: _secret_string(entry[name], path, f"{key}.{name}")
            for name in ("bearer", "username", "password")
            if name in entry
        }
        if has_basic and len(values) != 2:
            raise _fail(path, key, "username and password must be set together")
        csrf = entry.get("csrf", False)
        if not isinstance(csrf, bool):
            raise _fail(path, f"{key}.csrf", "must be a boolean")
        result[cred_id] = Credential(cred_id, tuple(parsed), csrf, **values)
    return result


def validate_cloudflare(document: dict[str, Any], path: Path) -> str:
    _warn_unknown(document, {"api_token"}, "", path)
    if "api_token" not in document:
        raise _fail(path, "api_token", "required")
    return _secret_string(document["api_token"], path, "api_token")


def curl_credentials(cfg: Config) -> dict[str, Credential]:
    path = cfg.resolve(cfg.data["secrets"]["curl"])
    return validate_curl(decrypt(path), path)


def cloudflare_token(cfg: Config) -> str:
    path = cfg.resolve(cfg.data["secrets"]["cloudflare"])
    return validate_cloudflare(decrypt(path), path)
