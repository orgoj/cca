"""cca watchlist: recurring checks, scheduled tasks and dated notes on Backlog.md.

The register is the project's Backlog.md; this command adds only what Backlog lacks
(doc-1 "Watchlist on Backlog.md"). It talks to Backlog only through the `backlog` CLI
and its versioned JSON output, run in the config dir with no BACKLOG_* variables.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import date, timedelta
from typing import Any

from cca import config, validate
from cca.output import CcaError, warn

TIMEOUT = 60
MAX_ERROR = 2000  # characters of backlog's stderr repeated in an error
JSON_SCHEMA = 1
REQUIRED_STATUSES = ("Note", "Done")
OPEN_EXCLUDED = ",".join(REQUIRED_STATUSES)
EVERY_RE = re.compile(r"every:([1-9][0-9]{0,2})d")
EVERY_MAX = 366
ID_RE = re.compile(r"[A-Za-z]+-[0-9]+(\.[0-9]+)*")
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
DATE_LABELS = ("from", "until")

EPILOG = """\
Conventions (plain Backlog.md, see the cca skill reference):
  recurring check  open task with label every:Nd; its due date is the next check;
                   optional until:YYYY-MM-DD ends the checking
  scheduled task   any open task with a due date
  note             task in status Note with optional from:/until:YYYY-MM-DD labels
                   (inclusive local dates)

Exit status: 0 OK; 1 a task has a malformed every:/from:/until: label (today, notes);
2 configuration, backlog or usage error.
"""


def today() -> date:
    return date.today()  # tests replace it


def iso_date(text: str) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {text!r} (expected YYYY-MM-DD)") from None


def task_id(text: str) -> str:
    if not ID_RE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"invalid task id {validate.display(text)!r}")
    return text.upper()


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = EPILOG
    sub = parser.add_subparsers(dest="action", metavar="ACTION", required=True)

    p = sub.add_parser("today", help="open tasks due today or earlier, then notes valid today")
    p.add_argument("--json", action="store_true", help="the backlog task objects as JSON")

    p = sub.add_parser("notes", help="notes valid on a date (default today)")
    p.add_argument("--on", type=iso_date, metavar="YYYY-MM-DD", help="date (local)")
    p.add_argument("--search", metavar="TEXT", help="passed to backlog task list --search")
    p.add_argument("--json", action="store_true", help="the backlog task objects as JSON")

    p = sub.add_parser("checked", help="a recurring check is done: move its due date")
    p.add_argument("id", type=task_id, metavar="ID", help="task id, e.g. TASK-12")
    p.add_argument("--json", action="store_true", help="the result as JSON")


# --- backlog CLI


def backlog_env() -> dict[str, str]:
    """The environment without BACKLOG_* (BACKLOG_CWD would point at another project)."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("BACKLOG_")}


def shown(args: list[str]) -> str:
    """The backlog subcommand for messages (never its free-text arguments)."""
    return " ".join(a for a in args[:2] if not a.startswith("-"))


def run_backlog(cwd: str, args: list[str]) -> str:
    """stdout of `backlog ARGS` run in cwd; CcaError (exit 2) on any failure."""
    binary = shutil.which("backlog")
    if binary is None:
        raise CcaError("backlog CLI not found on PATH (install Backlog.md)")
    try:
        result = subprocess.run(
            [binary, *args],
            cwd=cwd,
            env=backlog_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise CcaError(f"backlog {shown(args)} timed out after {TIMEOUT} s") from None
    except OSError as e:
        raise CcaError(f"cannot run backlog: {e.strerror}") from None
    if result.returncode != 0:
        output = result.stderr.strip() or result.stdout  # some errors go to stdout
        detail = " ".join(output.split())[:MAX_ERROR] or f"exit {result.returncode}"
        raise CcaError(f"backlog {shown(args)} failed: {validate.display(detail)}")
    return result.stdout


def backlog_json(cwd: str, args: list[str], kind: str) -> dict[str, Any]:
    out = run_backlog(cwd, [*args, "--json"])
    try:
        data = json.loads(out)
    except ValueError:
        raise CcaError(f"backlog {shown(args)} did not return JSON") from None
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != JSON_SCHEMA
        or data.get("kind") != kind
    ):
        raise CcaError(
            f"unsupported backlog JSON from {shown(args)} "
            f"(expected schemaVersion {JSON_SCHEMA}, kind {kind})"
        )
    return data


def list_tasks(cwd: str, args: list[str]) -> list[dict[str, Any]]:
    data = backlog_json(cwd, ["task", "list", *args], "task-list")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
        raise CcaError("unsupported backlog JSON from task list (tasks is not a list)")
    return tasks


# --- labels


class Labels:
    """The watchlist labels of one task; problems collected, never raised."""

    def __init__(self, task: dict[str, Any]):
        self.every: int | None = None
        self.dates: dict[str, date] = {}
        self.problems: list[str] = []
        labels = task.get("labels")
        labels = labels if isinstance(labels, list) else []
        seen: set[str] = set()
        for label in labels:
            if not isinstance(label, str):
                continue
            prefix, shown_label = label.partition(":")[0], validate.display(label)
            if prefix not in ("every", *DATE_LABELS) or ":" not in label:
                continue
            if prefix in seen:
                self.problems.append(f"duplicate {prefix}: label")
                continue
            seen.add(prefix)
            if prefix == "every":
                m = EVERY_RE.fullmatch(label)
                if m and int(m.group(1)) <= EVERY_MAX:
                    self.every = int(m.group(1))
                else:
                    self.problems.append(
                        f"malformed label {shown_label} (expected every:Nd, N 1-366)"
                    )
                continue
            try:
                self.dates[prefix] = iso_date(label.partition(":")[2])
            except argparse.ArgumentTypeError:
                self.problems.append(
                    f"malformed label {shown_label} (expected {prefix}:YYYY-MM-DD)"
                )
        if (
            "from" in self.dates
            and "until" in self.dates
            and self.dates["from"] > self.dates["until"]
        ):
            self.problems.append("from: is after until:")

    def valid_on(self, day: date) -> bool:
        start, end = self.dates.get("from"), self.dates.get("until")
        return (start is None or start <= day) and (end is None or day <= end)


def text(task: dict[str, Any], key: str) -> str:
    value = task.get(key)
    return validate.display(" ".join(value.split())) if isinstance(value, str) else "-"


def due_date(task: dict[str, Any]) -> date | None:
    value = task.get("dueDate")
    if not isinstance(value, str):
        return None
    try:
        return iso_date(value[:10])
    except argparse.ArgumentTypeError:
        return None


def report_problems(tasks: list[dict[str, Any]], labels: dict[int, Labels]) -> bool:
    found = False
    for task in tasks:
        for problem in labels[id(task)].problems:
            found = True
            warn(f"{text(task, 'id')}: {problem}")
    return found


# --- subcommands


def cmd_today(cwd: str, as_json: bool) -> int:
    day = today()
    open_tasks = list_tasks(cwd, ["--exclude-status", OPEN_EXCLUDED])
    notes = list_tasks(cwd, ["--status", "Note"])
    labels = {id(t): Labels(t) for t in (*open_tasks, *notes)}
    bad = report_problems(open_tasks, labels) | report_problems(notes, labels)
    due = [t for t in open_tasks if (d := due_date(t)) is not None and d <= day]
    due.sort(
        key=lambda t: (
            due_date(t),
            PRIORITY_RANK.get(str(t.get("priority")).lower(), len(PRIORITY_RANK)),
            text(t, "id"),
        )
    )
    valid = sort_notes([t for t in notes if labels[id(t)].valid_on(day)], labels)
    if as_json:
        print(
            json.dumps(validate.clean({"due": due, "notes": valid}), indent=2, ensure_ascii=False)
        )
        return 1 if bad else 0
    print("Due:")
    for task in due:
        lab = labels[id(task)]
        overdue = (day - due_date(task)).days
        fields = [text(task, "id"), due_date(task).isoformat(), f"+{overdue}d"]
        fields.append(f"every:{lab.every}d" if lab.every else "-")
        fields.append(text(task, "title"))
        line = " | ".join(fields)
        if lab.every and "until" in lab.dates and lab.dates["until"] < day:
            line += " [ended]"
        print(line)
    if not due:
        print("none")
    print_notes(valid, labels)
    return 1 if bad else 0


def sort_notes(notes: list[dict[str, Any]], labels: dict[int, Labels]) -> list[dict[str, Any]]:
    return sorted(
        notes,
        key=lambda t: (labels[id(t)].dates.get("from") or date.min, text(t, "id")),
    )


def print_notes(notes: list[dict[str, Any]], labels: dict[int, Labels]) -> None:
    print("Notes:")
    for task in notes:
        dates = labels[id(task)].dates
        span = "..".join(dates[k].isoformat() if k in dates else "*" for k in DATE_LABELS)
        print(f"{text(task, 'id')} | {span} | {text(task, 'title')}")
    if not notes:
        print("none")


def cmd_notes(cwd: str, on: date | None, search: str | None, as_json: bool) -> int:
    day = on or today()
    args = ["--status", "Note"]
    if search is not None:
        if validate.has_control(search):
            raise CcaError("--search contains a control character")
        args.append(f"--search={search}")  # one argv element: TEXT never reads as an option
    notes = list_tasks(cwd, args)
    labels = {id(t): Labels(t) for t in notes}
    bad = report_problems(notes, labels)
    valid = sort_notes([t for t in notes if labels[id(t)].valid_on(day)], labels)
    if as_json:
        print(json.dumps(validate.clean(valid), indent=2, ensure_ascii=False))
    else:
        print_notes(valid, labels)
    return 1 if bad else 0


def cmd_checked(cwd: str, ident: str, as_json: bool) -> int:
    task = backlog_json(cwd, ["task", "view", ident], "task-view").get("task")
    if not isinstance(task, dict):
        raise CcaError("unsupported backlog JSON from task view (no task)")
    status = task.get("status")
    if status in ("Done", "Note"):
        raise CcaError(f"{ident} has status {validate.display(str(status))}, not an open task")
    labels = Labels(task)
    if labels.problems:
        raise CcaError(f"{ident}: " + "; ".join(labels.problems))
    if labels.every is None:
        raise CcaError(f"{ident} is not a recurring check (no every:Nd label)")
    day = today()
    nxt = day + timedelta(days=labels.every)
    until = labels.dates.get("until")
    if until is not None and nxt > until:
        run_backlog(
            cwd,
            [
                "task",
                "edit",
                ident,
                "-s",
                "Done",
                "--comment",
                f"checked; ended (until: {until.isoformat()})",
                "--comment-author",
                "cca",
                "--plain",
            ],
        )
        result = {"id": ident, "status": "Done", "until": until.isoformat()}
        line = f"checked {ident}: done (until {until.isoformat()})"
    else:
        run_backlog(
            cwd,
            [
                "task",
                "edit",
                ident,
                "--due-date",
                nxt.isoformat(),
                "--comment",
                "checked",
                "--comment-author",
                "cca",
                "--plain",
            ],
        )
        result = {"id": ident, "dueDate": nxt.isoformat()}
        line = f"checked {ident}: next {nxt.isoformat()}"
    print(json.dumps(result, indent=2) if as_json else line)
    return 0


def run(args: argparse.Namespace) -> int:
    cwd = str(config.require(args.config).dir)
    if args.action == "today":
        return cmd_today(cwd, args.json)
    if args.action == "notes":
        return cmd_notes(cwd, args.on, args.search, args.json)
    return cmd_checked(cwd, args.id, args.json)
