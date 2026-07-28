"""Audit trail: JSONL logging with daily rotation and query.

Each operation writes one JSONL entry. Files rotate daily:
    logs/audit-2026-04-12.jsonl

Entry schema:
    ts           ISO-8601 timestamp with timezone
    agent        Agent name (empty string if not set)
    server       Target server name
    action       One of: run, read, session, list
    command      The command string (for action=run)
    exit_code    Command exit code (int, absent if N/A)
    duration_ms  Wall-clock duration in milliseconds (absent if N/A)
    validation   List of {hook, result, reason?} dicts
    redaction    List of {hook, result, reason?} dicts
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HookResult:
    """Result from a single hook execution (validation or redaction)."""

    hook: str
    result: str  # "approved", "denied", "pass", "block", "ask"
    reason: str = ""


@dataclass
class AuditEntry:
    """A single audit trail entry."""

    ts: str  # ISO-8601
    agent: str = ""
    server: str = ""
    action: str = ""  # run, read, session, list
    command: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None
    validation: list[dict[str, str]] = field(default_factory=list)
    redaction: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, omitting None values."""
        d = asdict(self)
        # Remove None values for cleaner JSONL
        return {k: v for k, v in d.items() if v is not None}

    def to_jsonl(self) -> str:
        """Serialize to a single JSONL line."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# AuditLogger — writes JSONL entries with daily rotation
# ---------------------------------------------------------------------------


def _today_filename() -> str:
    """Return today's audit filename: audit-YYYY-MM-DD.jsonl."""
    return f"audit-{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}.jsonl"


class AuditLogger:
    """Writes audit entries to daily-rotated JSONL files.

    Args:
        log_dir:  Directory for audit files (default: "logs").
        enabled:  If False, write() is a no-op.
    """

    def __init__(self, log_dir: str = "logs", enabled: bool = True) -> None:
        self.log_dir = Path(log_dir)
        self.enabled = enabled

    def _ensure_dir(self) -> None:
        """Create log directory if it doesn't exist."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self, ts: datetime | None = None) -> Path:
        """Return the path for the given timestamp's audit file."""
        when = ts or datetime.now(tz=timezone.utc)
        return self.log_dir / f"audit-{when.strftime('%Y-%m-%d')}.jsonl"

    def write(self, entry: AuditEntry) -> None:
        """Append an audit entry to today's JSONL file.

        No-op if self.enabled is False.
        """
        if not self.enabled:
            return

        self._ensure_dir()
        # Parse ts to determine correct date file
        ts = datetime.fromisoformat(entry.ts)
        path = self._log_path(ts)

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")

    def write_now(
        self,
        *,
        agent: str = "",
        server: str = "",
        action: str = "",
        command: str = "",
        exit_code: int | None = None,
        duration_ms: int | None = None,
        validation: list[HookResult] | None = None,
        redaction: list[HookResult] | None = None,
    ) -> AuditEntry:
        """Convenience: create an entry with current timestamp and write it."""
        entry = AuditEntry(
            ts=datetime.now(tz=timezone.utc).isoformat(),
            agent=agent,
            server=server,
            action=action,
            command=command,
            exit_code=exit_code,
            duration_ms=duration_ms,
            validation=[asdict(h) for h in (validation or [])],
            redaction=[asdict(h) for h in (redaction or [])],
        )
        self.write(entry)
        return entry


# ---------------------------------------------------------------------------
# AuditQuery — read and filter JSONL audit files
# ---------------------------------------------------------------------------


def _parse_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Parse JSONL lines into dicts, skipping blank/invalid lines."""
    entries: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip malformed lines
    return entries


class AuditQuery:
    """Read and filter audit JSONL files.

    Filters:
        today    — only entries from today
        server   — exact match on server field
        agent    — exact match on agent field
        action   — exact match on action field
        date     — specific date (YYYY-MM-DD)
    """

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = Path(log_dir)

    def _find_files(self, date: str | None = None) -> list[Path]:
        """Find audit JSONL files, optionally filtered by date."""
        if not self.log_dir.is_dir():
            return []

        if date:
            specific = self.log_dir / f"audit-{date}.jsonl"
            return [specific] if specific.is_file() else []

        # All audit-*.jsonl files
        return sorted(self.log_dir.glob("audit-*.jsonl"))

    def query(
        self,
        *,
        today: bool = False,
        server: str | None = None,
        agent: str | None = None,
        action: str | None = None,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query audit entries with optional filters.

        Returns list of entry dicts, newest first within each file.
        """
        if today:
            today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            files = self._find_files(date=today_str)
        else:
            files = self._find_files(date=date)

        all_entries: list[dict[str, Any]] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            all_entries.extend(_parse_entries(lines))

        # Apply filters
        if server is not None:
            all_entries = [e for e in all_entries if e.get("server") == server]
        if agent is not None:
            all_entries = [e for e in all_entries if e.get("agent") == agent]
        if action is not None:
            all_entries = [e for e in all_entries if e.get("action") == action]

        # Reverse so newest entries come first
        all_entries.reverse()
        return all_entries
