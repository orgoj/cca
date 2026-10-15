"""cca config show: the loaded config path and the validated document with defaults."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from cca import config

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", metavar="ACTION", required=True)
    sub.add_parser("show", help="print the config path and the validated document")


def run(args: argparse.Namespace) -> int:
    cfg = config.require(args.config)
    print(f"# {cfg.path}")
    print(dumps(cfg.data), end="")
    return 0


def _key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else json.dumps(key)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return "[" + ", ".join(_value(v) for v in value) + "]"


def dumps(data: dict[str, Any], prefix: str = "") -> str:
    """TOML for the validated document (strings, integers, booleans, arrays, tables)."""
    lines = [f"{_key(k)} = {_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    out = "\n".join(lines) + "\n" if lines else ""
    for key, value in data.items():
        if isinstance(value, dict):
            name = prefix + _key(key)
            has_values = any(not isinstance(v, dict) for v in value.values())
            if has_values or not value:
                out += f"\n[{name}]\n"
            out += dumps(value, name + ".")
    return out
