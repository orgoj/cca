"""cca watchlist migrate: one-shot conversion of a legacy watchlist.json into Backlog.md tasks.

Mapping and preflight: doc-1 "Watchlist on Backlog.md". Every item is checked before the
first write; tasks are created only through the backlog CLI, and the label
watchlist:<legacy id> makes a rerun skip the tasks that already exist.
"""

from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from cca import validate
from cca.commands import watchlist as wl
from cca.output import CcaError, warn

SCHEMA_MAJOR = 2
TYPES = ("routine", "incident", "task", "note")
STATES = ("active", "idle", "standby", "done")
PRIORITIES = {"p1": "high", "p2": "medium", "p3": "low"}
TAGS = {"effort": wl.EFFORTS, "change_risk": wl.CHANGE_RISKS, "window": wl.WINDOWS}
TEXTS = ("description", "status", "next_action", "blocked_on", "guide_keywords", "area")
TEXTS += ("risk", "file")
MULTILINE = ("description", "next_action")
NOTE_FORBIDDEN = ("next_action", "effort", "change_risk", "window", "blocked_on")
NOTE_FORBIDDEN += ("check_after", "monitor_until", "once", "last_check")
KNOWN = {"id", "type", "state", "name", "refs", "prio", "once", "last_check", "check_after"}
KNOWN |= {"monitor_until", "valid_from", "valid_until", *TEXTS, *TAGS}
LEGACY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
STATUSES = ("To Do", "Note", "Done")
LOCAL = None  # the system time zone; tests set a fixed one
LABEL = "watchlist:"


@dataclass
class Planned:
    legacy: str
    action: str  # new, exists, done, excluded
    title: str = ""
    status: str = ""
    description: str = ""
    labels: list[str] = field(default_factory=list)
    priority: str | None = None
    due: date | None = None
    refs: list[str] = field(default_factory=list)
    plan: str = ""
    warnings: list[str] = field(default_factory=list)


def timestamp(value: str) -> datetime:
    """An ISO timestamp; naive means UTC (as the legacy CLI stores it)."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def local_date(value: str, before: timedelta = timedelta(0)) -> date:
    """The date of an instant in the local time zone (Backlog dates carry no zone)."""
    return (timestamp(value) - before).astimezone(LOCAL).date()


def is_timestamp(value: Any) -> bool:
    try:
        return (
            isinstance(value, str) and DATE_RE.match(value) is not None and bool(timestamp(value))
        )
    except ValueError:
        return False


def is_date(value: Any) -> bool:
    try:
        return (
            isinstance(value, str)
            and DATE_RE.fullmatch(value) is not None
            and bool(date.fromisoformat(value))
        )
    except ValueError:
        return False


def bad_text(value: str, multiline: bool) -> bool:
    return validate.has_control(value.replace("\n", "").replace("\t", "") if multiline else value)


def slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9._-]", "-", ascii_value.lower())).strip("-.")


# --- preflight


def check_item(item: Any, where: str) -> list[str]:
    """Every problem of one item that would stop the migration."""
    if not isinstance(item, dict):
        return [f"{where}: not an object"]
    errors = []

    def bad(key: str, reason: str) -> None:
        errors.append(f"{where}: {key} {reason}")

    if not isinstance(item.get("id"), str) or not LEGACY_ID_RE.fullmatch(item["id"]):
        bad("id", "must match [A-Za-z0-9][A-Za-z0-9._-]*")
    if item.get("type") not in TYPES:
        bad("type", f"must be one of {', '.join(TYPES)}")
    if item.get("state") not in STATES:
        bad("state", f"must be one of {', '.join(STATES)}")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip() or bad_text(name, False):
        bad("name", "must be a non-empty one-line string")
    for key in TEXTS:
        value = item.get(key)
        if value is not None and (not isinstance(value, str) or bad_text(value, key in MULTILINE)):
            bad(key, "must be a string without control characters")
    for key, allowed in (*TAGS.items(), ("prio", tuple(PRIORITIES))):
        if item.get(key) is not None and item.get(key) not in allowed:
            bad(key, f"must be one of {', '.join(allowed)}")
    refs = item.get("refs", [])
    if not isinstance(refs, list) or not all(
        isinstance(r, str) and r and "," not in r and not validate.has_control(r) for r in refs
    ):
        bad("refs", "must be a list of non-empty paths without commas or control characters")
    if item.get("once") is not None and not isinstance(item.get("once"), bool):
        bad("once", "must be true or false")
    last = item.get("last_check")
    if last is not None and last != "never" and not is_timestamp(last):
        bad("last_check", "must be never or an ISO timestamp")
    if item.get("check_after") is not None and not is_timestamp(item["check_after"]):
        bad("check_after", "must be an ISO timestamp")
    if item.get("monitor_until") is not None and not is_timestamp(item["monitor_until"]):
        bad("monitor_until", "must be an ISO timestamp")
    for key in ("valid_from", "valid_until"):
        if item.get(key) is not None and not is_date(item[key]):
            bad(key, "must be YYYY-MM-DD")
    if is_date(item.get("valid_from")) and is_date(item.get("valid_until")):
        if item["valid_from"] > item["valid_until"]:
            bad("valid_from", "is after valid_until")
    if item.get("type") == "note":
        if item.get("state") not in ("idle", "done"):
            bad("state", "of a note must be idle or done")
        for key in NOTE_FORBIDDEN:
            if item.get(key) is not None:
                bad(key, "is not allowed on a note")
    elif item.get("valid_from") is not None or item.get("valid_until") is not None:
        bad("valid_from/valid_until", "are only allowed on notes")
    if item.get("type") == "incident" and not (isinstance(item.get("file"), str) and item["file"]):
        bad("file", "is required for an incident")
    return errors


def preflight(data: Any, excludes: list[str]) -> list[dict[str, Any]]:
    """The items, or CcaError listing every problem."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise CcaError("watchlist: expected an object with an items list")
    version = str(data.get("version", ""))
    if version.partition(".")[0] != str(SCHEMA_MAJOR):
        raise CcaError(
            f"watchlist: schema v{validate.display(version) or '?'} is not supported "
            f"(v{SCHEMA_MAJOR} only; upgrade a v1 file with the legacy cca-watchlist migrate)"
        )
    items = data["items"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        ident = item.get("id") if isinstance(item, dict) else None
        where = f"item {index + 1}" + (
            f" ({validate.display(ident)})" if isinstance(ident, str) else ""
        )
        errors += check_item(item, where)
        if isinstance(ident, str):
            if ident in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(ident)
    for ident in excludes:
        if ident not in seen:
            errors.append(f"--exclude {validate.display(ident)}: no such item")
    if errors:
        raise CcaError("watchlist has problems, nothing written:\n  " + "\n  ".join(errors))
    return items


# --- mapping


class Refs:
    """Legacy ref lookup (relative to the watchlist), written relative to the config dir."""

    def __init__(self, watchlist: Path, config_dir: str):
        parent = Path(os.path.abspath(watchlist)).parent
        self.root = parent.parent if parent.name == "cca" else parent
        self.bases = [parent]
        if parent.name != "cca" and (parent / "cca").is_dir():
            self.bases.append(parent / "cca")
        self.config_dir = os.path.abspath(config_dir)

    def candidates(self, ref: str) -> list[Path]:
        path = Path(ref).expanduser()
        if path.is_absolute():
            return [path]
        found = [self.root / path, *(base / path for base in self.bases)]
        if "/" not in ref:
            name = glob.escape(ref)
            for base in self.bases:
                found += [base / "incidents" / ref, base / "deniky" / ref]
                found += sorted(base.glob(f"incidents/archive/*/{name}"))
                found += sorted(base.glob(f"guides/**/{name}"))
        return found

    def resolve(self, ref: str) -> str | None:
        for candidate in self.candidates(ref):
            if candidate.exists():
                try:
                    return Path(os.path.relpath(candidate, self.config_dir)).as_posix()
                except ValueError:  # another drive on Windows
                    return candidate.as_posix()
        return None


def description(item: dict[str, Any]) -> str:
    meta = []
    for key, title in (("status", "Status"), ("blocked_on", "Blocked on")):
        if (item.get(key) or "").strip():
            meta.append(f"{title}: {item[key].strip()}")
    keywords = (item.get("guide_keywords") or "").strip()
    if keywords and keywords != item["name"].lower():
        meta.append(f"Keywords: {keywords}")
    if item.get("check_after"):
        meta.append(f"Check after: {timestamp(item['check_after']).isoformat()}")
    origin = f"Migrated from watchlist item {item['id']}"
    if "last_check" in item:
        origin += f", last check {item.get('last_check') or 'never'}"
    meta.append(origin + ".")
    return "\n\n".join(x for x in ((item.get("description") or "").strip(), "\n".join(meta)) if x)


def convert(item: dict[str, Any], refs: Refs, day: date) -> Planned:
    p = Planned(item["id"], "new", title=" ".join(item["name"].split()))
    p.description = description(item)
    p.priority = PRIORITIES.get(item.get("prio") or "")
    p.labels.append(LABEL + item["id"])
    for key, value in (("area", item.get("area")), ("risk", item.get("risk"))):
        if (value or "").strip():
            if slug(value):
                p.labels.append(f"{key}:{slug(value)}")
            else:
                p.warnings.append(f"{key} {validate.display(value)!r} has no label form, dropped")
    for key, prefix in (("effort", "effort"), ("change_risk", "change-risk"), ("window", "window")):
        if item.get(key):
            p.labels.append(f"{prefix}:{item[key]}")
    if item["type"] == "incident":
        p.labels.append("incident")
    if (item.get("blocked_on") or "").strip():
        p.labels.append("blocked:external")
    sources = ([item["file"]] if item["type"] == "incident" else []) + list(item.get("refs") or [])
    for ref in dict.fromkeys(sources):
        resolved = refs.resolve(ref)
        if resolved is None:
            p.warnings.append(f"ref not found, kept as is: {validate.display(ref)}")
        if (resolved or ref) not in p.refs:
            p.refs.append(resolved or ref)
    if item["type"] == "note":
        p.status = "Note"
        for key, prefix in (("valid_from", "from"), ("valid_until", "until")):
            if item.get(key):
                p.labels.append(f"{prefix}:{item[key]}")
        return p
    p.status = "To Do"
    p.plan = (item.get("next_action") or "").strip()
    daily = item["state"] == "active" and (
        item["type"] != "incident" or (item.get("status") or "").strip() == "monitoring"
    )
    after = local_date(item["check_after"]) if item.get("check_after") else None
    if not daily:
        # outside the daily check: today skips idle/standby, the due date only defers next
        p.labels.append("standby" if item["state"] == "standby" else "idle")
        p.due = after
        if item.get("monitor_until"):
            p.warnings.append("monitor_until dropped (not a daily check)")
        return p
    starts = [after] if after else []
    if item.get("last_check") not in (None, "never"):
        starts.append(local_date(item["last_check"]) + timedelta(days=1))
    p.due = max(starts) if starts else day
    if item.get("monitor_until"):
        # monitor_until is exclusive, until: an inclusive date
        until = local_date(item["monitor_until"], timedelta(microseconds=1))
        if item.get("once"):
            p.warnings.append("monitor_until dropped (a once item has no recurrence to end)")
        else:
            p.labels.append(f"until:{until.isoformat()}")
            if until < day:
                p.warnings.append(f"monitoring ended {until.isoformat()} (today shows it [ended])")
    if not item.get("once"):
        p.labels.insert(1, "every:1d")
    return p


# --- backlog


def existing_tasks(cwd: str) -> dict[str, dict[str, Any]]:
    """Tasks carrying a watchlist:<id> label, by legacy id (one-to-one, else CcaError)."""
    found: dict[str, dict[str, Any]] = {}
    for task in wl.list_tasks(cwd, []):
        labels = task.get("labels") if isinstance(task.get("labels"), list) else []
        mine = [x for x in labels if isinstance(x, str) and x.startswith(LABEL)]
        if len(mine) > 1 or (mine and mine[0] == LABEL):
            shown = validate.display(", ".join(mine))
            raise CcaError(f"{wl.text(task, 'id')} needs exactly one {LABEL}<id> label: {shown}")
        if mine:
            legacy = mine[0][len(LABEL) :]
            if legacy in found:
                raise CcaError(f"two tasks carry the label {validate.display(mine[0])}")
            found[legacy] = task
    return found


def check_statuses(cwd: str) -> None:
    names = {s.strip() for s in wl.run_backlog(cwd, ["config", "get", "statuses"]).split(",")}
    missing = [s for s in STATUSES if s not in names]
    if missing:
        raise CcaError(
            "backlog statuses lack " + ", ".join(missing) + " (statuses in backlog/config.yml)"
        )


def create_args(p: Planned) -> list[str]:
    args = ["task", "create", f"--description={p.description}", f"--status={p.status}"]
    args.append("--labels=" + ",".join(p.labels))
    if p.priority:
        args.append(f"--priority={p.priority}")
    if p.due:
        args.append(f"--due-date={p.due.isoformat()}")
    args += [f"--ref={r}" for r in p.refs]
    return [*args, "--plain", "--", p.title]


def line(p: Planned) -> str:
    if p.action in ("done", "excluded"):
        return f"{p.legacy} -> skipped ({p.action})"
    fields = [p.status, p.due.isoformat() if p.due else "-", ",".join(p.labels), p.title]
    return f"{p.legacy} -> {p.action} | " + " | ".join(validate.display(f) for f in fields)


def run(cwd: str, file: str, apply: bool, excludes: list[str]) -> int:
    path = Path(file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise CcaError(f"cannot read {validate.display(file)}: {e.strerror}") from None
    except ValueError as e:
        raise CcaError(f"{validate.display(file)} is not JSON: {e}") from None
    items = preflight(data, excludes)
    check_statuses(cwd)
    existing = existing_tasks(cwd)
    refs, day = Refs(path, cwd), wl.today()
    planned = []
    for item in items:
        if item["id"] in excludes:
            planned.append(Planned(item["id"], "excluded"))
        elif item["state"] == "done":
            planned.append(Planned(item["id"], "done"))
        else:
            p = convert(item, refs, day)
            p.action = "exists" if item["id"] in existing else "new"
            planned.append(p)
            for unknown in sorted(set(item) - KNOWN):
                p.warnings.append(f"unknown key {validate.display(unknown)} not migrated")
    warnings = 0
    for p in planned:
        print(line(p))
        for message in p.warnings:
            warnings += 1
            warn(f"{p.legacy}: {message}")
    count = {a: sum(p.action == a for p in planned) for a in ("new", "exists", "done", "excluded")}
    summary = f"items {len(planned)}: " + ", ".join(f"{a} {n}" for a, n in count.items())
    if not apply:
        print(f"{summary}; warnings {warnings} (dry run, nothing written; --apply creates them)")
        return 1 if warnings else 0
    for p in planned:
        if p.action == "new":
            wl.run_backlog(cwd, create_args(p))
    created = existing_tasks(cwd)
    for p in planned:
        if p.action not in ("new", "exists"):
            continue
        task = created.get(p.legacy)
        if task is None:
            raise CcaError(f"{p.legacy}: created task not found by its {LABEL} label")
        ident = task.get("id")
        if not isinstance(ident, str) or not wl.ID_RE.fullmatch(ident):
            raise CcaError(
                f"unsupported backlog JSON from task list (task id {wl.text(task, 'id')})"
            )
        if p.action == "new":
            print(f"created {ident} <- {p.legacy}")
        if p.plan and (p.action == "new" or not wl.plan(wl.view(cwd, task))):
            wl.run_backlog(cwd, ["task", "edit", ident, f"--plan={p.plan}", "--plain"])
            if p.action == "exists":
                print(f"plan set {ident} <- {p.legacy}")
    print(f"{summary}; warnings {warnings}")
    return 1 if warnings else 0
