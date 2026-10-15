"""User-facing errors and warnings (stderr, `cca:` prefix)."""

from __future__ import annotations

import sys


class CcaError(Exception):
    """An expected failure: printed as `cca: error: <message>`, exit `code`."""

    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def warn(message: str) -> None:
    print(f"cca: warning: {message}", file=sys.stderr)


def error(message: str) -> None:
    print(f"cca: error: {message}", file=sys.stderr)
