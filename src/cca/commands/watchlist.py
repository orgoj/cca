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
NOT_WORK = ("Idea",)  # open statuses that never count as work (ready, next, Priority)
OUTSIDE_DAILY = ("idle", "standby")  # labels: never in Due; a due date only defers next
EFFORTS = ("e15", "e1h", "e4h", "exl")
CHANGE_RISKS = ("r0", "r1", "r2", "r3")
WINDOWS = ("wany", "woff", "wnight", "wfreeze")
TAG_LABELS = {"effort": EFFORTS, "change-risk": CHANGE_RISKS, "window": WINDOWS}
TIME_EFFORT = {"15m": "e15", "1h": "e1h", "4h": "e4h"}
MINIMUM_WINDOW = {"r0": "wany", "r1": "wany", "r2": "woff", "r3": "wnight"}
SHOWN = 20  # rows of ready and the Priority section

EPILOG = """\
Conventions (plain Backlog.md, see the cca skill reference):
  recurring check  open task with label every:Nd; its due date is the next check;
                   optional until:YYYY-MM-DD ends the checking
  scheduled task   any open task with a due date, except idle/standby ones
  outside daily    label idle (backlog work) or standby (waiting for an event): never
                   due in today; a due date only means "not before" for next/Priority
  note             task in status Note with optional from:/until:YYYY-MM-DD labels
                   (inclusive local dates)
  work tags        labels effort:e15|e1h|e4h|exl, change-risk:r0-r3,
                   window:wany|woff|wnight|wfreeze, area:NAME;
                   blocked:* or an unfinished dependency = blocked
  next action      the task's Implementation Plan (backlog task edit ID --plan TEXT)

Exit status: 0 OK; 1 a task has a malformed watchlist label, or migrate warned;
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
    p.add_argument("--expired", action="store_true", help="notes whose until: is before the date")
    p.add_argument("--search", metavar="TEXT", help="passed to backlog task list --search")
    p.add_argument("--json", action="store_true", help="the backlog task objects as JSON")

    p = sub.add_parser("checked", help="a recurring check is done: move its due date")
    p.add_argument("id", type=task_id, metavar="ID", help="task id, e.g. TASK-12")
    p.add_argument("--json", action="store_true", help="the result as JSON")

    for name, help_text in (
        ("ready", "open work fitting the available time, window and change risk"),
        ("next", "the first ready task with a next action and no future due date"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--time", choices=tuple(TIME_EFFORT), default="1h", help="(default 1h)")
        p.add_argument("--window", choices=WINDOWS, default="wany", help="(default wany)")
        p.add_argument("--max-change-risk", choices=CHANGE_RISKS, metavar="r0..r3")
        p.add_argument("--area", metavar="NAME", help="only tasks labelled area:NAME")
        if name == "ready":
            p.add_argument("--include-blocked", action="store_true", help="keep blocked tasks")
            p.add_argument("--verbose", action="store_true", help="show each next action")
        p.add_argument("--json", action="store_true", help="the backlog task objects as JSON")

    p = sub.add_parser("migrate", help="one-shot conversion of a legacy watchlist.json")
    p.add_argument("file", metavar="FILE", help="watchlist.json (schema v2), relative to the CWD")
    p.add_argument("--apply", action="store_true", help="create the tasks (default: dry run)")
    p.add_argument(
        "--exclude", action="append", default=[], metavar="ID", help="skip this item (repeatable)"
    )


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
        self.tags: dict[str, str] = {}
        self.problems: list[str] = []
        labels = task.get("labels")
        self.names = [x for x in labels if isinstance(x, str)] if isinstance(labels, list) else []
        seen: set[str] = set()
        for label in self.names:
            prefix, shown_label = label.partition(":")[0], validate.display(label)
            if prefix not in ("every", *DATE_LABELS, *TAG_LABELS) or ":" not in label:
                continue
            if prefix in seen:
                self.problems.append(f"duplicate {prefix}: label")
                continue
            seen.add(prefix)
            if prefix in TAG_LABELS:
                value = label.partition(":")[2]
                if value in TAG_LABELS[prefix]:
                    self.tags[prefix] = value
                else:
                    allowed = "|".join(TAG_LABELS[prefix])
                    self.problems.append(
                        f"malformed label {shown_label} (expected {prefix}:{allowed})"
                    )
                continue
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

    def window(self) -> str | None:
        """The stricter of window: and the minimum for change-risk: (legacy effective window)."""
        window = self.tags.get("window")
        minimum = MINIMUM_WINDOW.get(self.tags.get("change-risk", ""))
        if window is None or minimum is None:
            return window or minimum
        return max(window, minimum, key=WINDOWS.index)

    def blocked(self, task: dict[str, Any]) -> bool:
        """A blocked:* label or an unfinished Backlog dependency (isReady false)."""
        ready = task.get("isReady")
        if not isinstance(ready, bool):
            raise CcaError(
                f"unsupported backlog JSON from task list ({text(task, 'id')}: no isReady)"
            )
        return not ready or any(x.startswith("blocked:") for x in self.names)


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


# --- work selection (legacy ready / next / agenda)


def id_key(task: dict[str, Any]) -> tuple:
    """TASK-9 before TASK-10."""
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"([0-9]+)", text(task, "id")))


def priority_rank(task: dict[str, Any]) -> int:
    return PRIORITY_RANK.get(str(task.get("priority")).lower(), len(PRIORITY_RANK))


def select_ready(
    tasks: list[dict[str, Any]], labels: dict[int, Labels], args: argparse.Namespace
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Open work fitting --time/--window/--max-change-risk, and the tasks without effort:."""
    limit = EFFORTS.index(TIME_EFFORT[args.time])
    ready, untagged = [], []
    for task in tasks:
        lab = labels[id(task)]
        if (
            task.get("status") in NOT_WORK
            or "standby" in lab.names
            or (args.area is not None and f"area:{args.area}" not in lab.names)
            or (lab.blocked(task) and not getattr(args, "include_blocked", False))
        ):
            continue
        effort = lab.tags.get("effort")
        if effort is None:
            untagged.append(task)
            continue
        window, risk = lab.window(), lab.tags.get("change-risk")
        if (
            effort == "exl"
            or EFFORTS.index(effort) > limit
            or window is None
            or WINDOWS.index(window) > WINDOWS.index(args.window)
            or (
                args.max_change_risk is not None
                and (
                    risk is None
                    or CHANGE_RISKS.index(risk) > CHANGE_RISKS.index(args.max_change_risk)
                )
            )
        ):
            continue
        ready.append(task)
    ready.sort(
        key=lambda t: (priority_rank(t), EFFORTS.index(labels[id(t)].tags["effort"]), id_key(t))
    )
    untagged.sort(key=id_key)
    return ready, untagged


def view(cwd: str, task: dict[str, Any]) -> dict[str, Any]:
    """The full task (task list JSON has no Implementation Plan)."""
    ident = task.get("id")
    if not isinstance(ident, str) or not ID_RE.fullmatch(ident):
        raise CcaError(f"unsupported backlog JSON from task list (task id {text(task, 'id')})")
    full = backlog_json(cwd, ["task", "view", ident], "task-view").get("task")
    if not isinstance(full, dict):
        raise CcaError("unsupported backlog JSON from task view (no task)")
    return full


def plan(task: dict[str, Any]) -> str:
    value = task.get("implementationPlan")
    return value.strip() if isinstance(value, str) else ""


def actionable(cwd: str, ready: list[dict[str, Any]]):
    """(task, full task) of ready tasks with a next action and no future due date, in order."""
    day = today()
    for task in ready:
        due = due_date(task)
        if due is not None and due > day:
            continue
        full = view(cwd, task)
        if plan(full):
            yield task, full


def work_line(task: dict[str, Any], lab: Labels) -> str:
    fields = [text(task, "id"), text(task, "priority").lower(), lab.tags.get("effort", "-")]
    return " | ".join([*fields, lab.window() or "-", text(task, "title")])


def print_rows(rows: list[str], more: str) -> None:
    for row in rows[:SHOWN]:
        print(row)
    if len(rows) > SHOWN:
        print(f"... {len(rows) - SHOWN} more ({more})")
    if not rows:
        print("none")


def open_work(cwd: str) -> tuple[list[dict[str, Any]], dict[int, Labels], bool]:
    tasks = list_tasks(cwd, ["--exclude-status", OPEN_EXCLUDED])
    labels = {id(t): Labels(t) for t in tasks}
    return tasks, labels, report_problems(tasks, labels)


def agenda_args() -> argparse.Namespace:
    """The legacy agenda defaults: 1h, wany, any change risk, every area."""
    return argparse.Namespace(time="1h", window="wany", max_change_risk=None, area=None)


# --- subcommands


def cmd_today(cwd: str, as_json: bool) -> int:
    day = today()
    open_tasks, labels, bad = open_work(cwd)
    notes = list_tasks(cwd, ["--status", "Note"])
    labels.update({id(t): Labels(t) for t in notes})
    bad |= report_problems(notes, labels)
    due = [
        t
        for t in open_tasks
        if (d := due_date(t)) is not None
        and d <= day
        and t.get("status") not in NOT_WORK
        and not set(OUTSIDE_DAILY) & set(labels[id(t)].names)
    ]
    due.sort(key=lambda t: (due_date(t), priority_rank(t), id_key(t)))
    due_ids = {id(t) for t in due}
    ready, _ = select_ready(open_tasks, labels, agenda_args())
    high = [t for t in ready if priority_rank(t) == 0 and id(t) not in due_ids]
    priority = list(actionable(cwd, high))
    valid = sort_notes([t for t in notes if labels[id(t)].valid_on(day)], labels)
    if as_json:
        body = {"due": due, "priority": [full for _, full in priority], "notes": valid}
        print(json.dumps(validate.clean(body), indent=2, ensure_ascii=False))
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
    print("Priority:")
    print_rows([work_line(t, labels[id(t)]) for t, _ in priority], "cca watchlist ready")
    print_notes(valid, labels)
    return 1 if bad else 0


def sort_notes(notes: list[dict[str, Any]], labels: dict[int, Labels]) -> list[dict[str, Any]]:
    return sorted(notes, key=lambda t: (labels[id(t)].dates.get("from") or date.min, id_key(t)))


def print_notes(notes: list[dict[str, Any]], labels: dict[int, Labels]) -> None:
    print("Notes:")
    for task in notes:
        dates = labels[id(task)].dates
        span = "..".join(dates[k].isoformat() if k in dates else "*" for k in DATE_LABELS)
        print(f"{text(task, 'id')} | {span} | {text(task, 'title')}")
    if not notes:
        print("none")


def cmd_notes(cwd: str, on: date | None, expired: bool, search: str | None, as_json: bool) -> int:
    day = on or today()
    args = ["--status", "Note"]
    if search is not None:
        if validate.has_control(search):
            raise CcaError("--search contains a control character")
        args.append(f"--search={search}")  # one argv element: TEXT never reads as an option
    notes = list_tasks(cwd, args)
    labels = {id(t): Labels(t) for t in notes}
    bad = report_problems(notes, labels)
    if expired:
        valid = [t for t in notes if labels[id(t)].dates.get("until", date.max) < day]
        valid.sort(key=lambda t: (labels[id(t)].dates["until"], id_key(t)))
    else:
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


def cmd_ready(cwd: str, args: argparse.Namespace) -> int:
    tasks, labels, bad = open_work(cwd)
    ready, untagged = select_ready(tasks, labels, args)
    if args.json:
        body = {
            "ready": [view(cwd, t) for t in ready],
            "untagged": [view(cwd, t) for t in untagged],
        }
        print(json.dumps(validate.clean(body), indent=2, ensure_ascii=False))
        return 1 if bad else 0
    rows = []
    for task in ready:
        row = work_line(task, labels[id(task)])
        if args.verbose and len(rows) < SHOWN:
            action = plan(view(cwd, task))
            row += f"\n  next: {validate.display(' '.join(action.split())) if action else '-'}"
        rows.append(row)
    print_rows(rows, "--json lists all")
    print(f"untagged (no effort:): {len(untagged)}")
    return 1 if bad else 0


def cmd_next(cwd: str, args: argparse.Namespace) -> int:
    tasks, labels, bad = open_work(cwd)
    ready, _ = select_ready(tasks, labels, args)
    found = next(actionable(cwd, ready), None)
    if args.json:
        print(json.dumps(validate.clean(found and found[1]), indent=2, ensure_ascii=False))
    elif found is None:
        print("none")
    else:
        print(work_line(found[0], labels[id(found[0])]))
        print(f"  next: {validate.display(' '.join(plan(found[1]).split()))}")
    return 1 if bad else 0


def run(args: argparse.Namespace) -> int:
    cwd = str(config.require(args.config).dir)
    if args.action == "today":
        return cmd_today(cwd, args.json)
    if args.action == "notes":
        return cmd_notes(cwd, args.on, args.expired, args.search, args.json)
    if args.action == "ready":
        return cmd_ready(cwd, args)
    if args.action == "next":
        return cmd_next(cwd, args)
    if args.action == "migrate":
        from cca import watchlist_migrate

        return watchlist_migrate.run(cwd, args.file, args.apply, args.exclude)
    return cmd_checked(cwd, args.id, args.json)
