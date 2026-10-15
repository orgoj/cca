"""cca hetrix: HetrixTools uptime monitors, outages, server agent metrics and blacklists.

Talks to the HetrixTools API v3 with the bearer credential that the project's curl
secrets file allows for the API origin (doc-2 `secrets.curl`). The token is sent only as
a header that is not repeated on redirects, and redirects are not followed at all.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from cca import config, secrets, validate
from cca.output import CcaError

ORIGIN = "https://api.hetrixtools.com"
API_BASE = ORIGIN + "/v3"  # tests point it at a local server
TIMEOUT = 20  # socket timeout of one request
SLACK = 10  # added for the whole request (slow headers, trickled body)
MAX_BODY = 32 * 1024 * 1024  # response cap
MAX_ERROR_BODY = 64 * 1024
MAX_PAGES = 50  # list pages followed before giving up
FAIL_LOG_PAGES = 20  # location fail log pages (each up to FAIL_LOG_MINUTES minutes with failures)
FAIL_LOG_MINUTES = 100  # API maximum
SLOW_MS, VERY_SLOW_MS = 3000, 5000
DISK_WARNING, DISK_CRITICAL = 80, 90
# listings on these RBLs are reported as warnings and do not fail `blacklist`
WARN_RBLS = frozenset({"dnsbl-2.uceprotect.net", "dnsbl-3.uceprotect.net"})
MONITOR_ID_RE = re.compile(r"[A-Za-z0-9]{32}")
TARGET_RE = re.compile(r"[A-Za-z0-9.-]{1,253}")  # API filter: IPv4 address or domain
RELATIVE_RE = re.compile(r"(\d{1,6})([mhd])")
UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}
TIME_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M")
SIGNATURE_SUBS = (  # parts of a failure message that differ between otherwise equal errors
    re.compile(r" \(\d+ms\)$"),
    re.compile(r" after \d+ milliseconds.*$"),
    re.compile(r" Error 0: *$"),
)

EPILOG = """\
Times (--since, --until) are relative (30m, 12h, 7d) or local dates (YYYY-MM-DD,
"YYYY-MM-DD HH:MM"). MONITOR is a 32-character monitor id or a case-insensitive part of
a monitor name. The API key is the bearer credential for https://api.hetrixtools.com in
the project's curl secrets file.

Exit status: 0 OK; 1 a monitor is DOWN (status), a target is on a blacklist other than
dnsbl-2/dnsbl-3.uceprotect.net (blacklist), or no monitor matches; 2 API, configuration
or usage error.
"""


# --- time


def now() -> int:
    return int(time.time())


def parse_time(text: str) -> tuple[int, str]:
    """(timestamp, text) of a relative (12h) or local (YYYY-MM-DD [HH:MM]) time."""
    m = RELATIVE_RE.fullmatch(text)
    if m:
        return now() - int(m.group(1)) * UNIT_SECONDS[m.group(2)], text
    for fmt in TIME_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return int(time.mktime(parsed.timetuple())), text
    raise argparse.ArgumentTypeError(
        f"invalid time '{validate.display(text)}' (use 30m, 12h, 7d, YYYY-MM-DD"
        " or 'YYYY-MM-DD HH:MM')"
    )


def local_time(ts: Any) -> str:
    if not isinstance(ts, int):
        return "unknown time"
    return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(ts))


def duration(seconds: int) -> str:
    seconds = max(seconds, 0)
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def window(args: argparse.Namespace, default_since: int, default_text: str) -> tuple[int, int, str]:
    """(since, until, period text) from --since/--until."""
    if args.since is not None:
        since, text = args.since[0], f"since {args.since[1]}"
    else:
        since, text = now() - default_since, default_text
    until = now()
    if args.until is not None:
        until = args.until[0]
        text += f" until {args.until[1]}"
    if since > until:
        raise CcaError("--since must be before --until")
    return since, until, text


# --- API access


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the redirect response becomes an HTTP error


class Api:
    def __init__(self, token: str):
        self._token = token

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Parsed JSON object with every string escaped for printing; CcaError on failure."""
        query = "?" + urllib.parse.urlencode(params) if params else ""
        label = f"HetrixTools API GET {path}"
        outcome: list = []
        worker = threading.Thread(
            target=self._read, args=(API_BASE + path + query, label, outcome), daemon=True
        )
        worker.start()
        worker.join(TIMEOUT + SLACK)
        if not outcome:  # still running: abandoned, it stops at the cap or the socket timeout
            raise CcaError(f"{label}: timed out")
        if isinstance(outcome[0], CcaError):
            raise outcome[0]
        status, body = outcome[0]
        if status != 200:
            raise CcaError(f"{label}: HTTP {status}{_api_message(body)}{_hint(status)}")
        if len(body) > MAX_BODY:
            raise CcaError(f"{label}: response larger than {MAX_BODY} bytes")
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:  # includes UnicodeDecodeError
            raise CcaError(f"{label}: invalid JSON") from None
        if not isinstance(data, dict):
            raise CcaError(f"{label}: unexpected response (not a JSON object)")
        return validate.clean(data)

    def _read(self, url: str, label: str, outcome: list) -> None:
        # no proxy or other settings from the environment, no redirects with the token
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        request.add_unredirected_header("Authorization", f"Bearer {self._token}")
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                outcome.append((response.status, _read_capped(response, MAX_BODY)))
        except urllib.error.HTTPError as e:
            try:
                body = _read_capped(e, MAX_ERROR_BODY)
            except (OSError, http.client.HTTPException, AttributeError):  # AttributeError: no fp
                body = b""
            outcome.append((e.code, body))
        except (OSError, http.client.HTTPException) as e:
            reason = getattr(e, "reason", None) or e
            outcome.append(CcaError(f"{label}: {validate.display(str(reason))}"))

    def pages(self, path: str, key: str, params: dict[str, Any], per_page: int) -> list[dict]:
        """All items of a paginated list (meta.pagination.next)."""
        items: list[dict] = []
        page = 1
        while True:
            data = self.get(path, {**params, "per_page": per_page, "page": page})
            batch = data.get(key)
            if not isinstance(batch, list):
                raise CcaError(f"HetrixTools API GET {path}: response has no '{key}' list")
            items += [item for item in batch if isinstance(item, dict)]
            meta = data.get("meta")
            pagination = meta.get("pagination") if isinstance(meta, dict) else None
            following = pagination.get("next") if isinstance(pagination, dict) else None
            if not isinstance(following, int) or following <= page:
                return items
            if following > MAX_PAGES:
                raise CcaError(f"HetrixTools API GET {path}: more than {MAX_PAGES} pages")
            page = following


def _read_capped(stream: Any, limit: int) -> bytes:
    body = bytearray()
    while len(body) <= limit:
        chunk = stream.read1(65536)
        if not chunk:
            break
        body += chunk
    return bytes(body)


def _api_message(body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError:
        return ""
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, str) or not message:
        return ""
    return f": {validate.display(message[:200])}"


def _hint(status: int) -> str:
    if status == 401:
        return " (check the HetrixTools credential in the curl secrets file)"
    if status == 403:
        return " (allow this API call for the key in the HetrixTools API key settings)"
    return ""


def connect(args: argparse.Namespace) -> Api:
    cfg = config.require(args.config)
    origin, _tail = validate.parse_https_url(ORIGIN)
    matches = [c for c in secrets.curl_credentials(cfg).values() if origin in c.origins]
    if len(matches) != 1:
        found = "no credential" if not matches else "several credentials"
        raise CcaError(f"{found} in the curl secrets file allow {ORIGIN}, exactly one must")
    cred = matches[0]
    if cred.bearer is None:
        raise CcaError(f"credential '{cred.id}' for {ORIGIN} must be a bearer token")
    return Api(cred.bearer)


# --- uptime monitors


def monitors(api: Api, **filters: Any) -> list[dict]:
    return api.pages("/uptime-monitors", "monitors", filters, 200)


def find_monitor(api: Api, term: str) -> dict:
    """The monitor with this id, or the one whose name contains the term (case-insensitive)."""
    if MONITOR_ID_RE.fullmatch(term):
        found = monitors(api, id=term)
        if not found:
            raise CcaError(f"no monitor with id {term}", code=1)
        return found[0]
    needle = term.casefold()
    everything = monitors(api)
    matches = [m for m in everything if needle in str(m.get("name", "")).casefold()]
    exact = [m for m in matches if str(m.get("name", "")).casefold() == needle]
    if len(exact) == 1:
        return exact[0]
    if not matches:
        raise CcaError(f"no monitor name contains '{validate.display(term)}'", code=1)
    if len(matches) > 1:
        names = ", ".join(sorted(str(m.get("name")) for m in matches))
        raise CcaError(f"several monitors match '{validate.display(term)}': {names}", code=1)
    return matches[0]


def monitor_id(monitor: dict) -> str:
    value = monitor.get("id")
    if not isinstance(value, str) or not MONITOR_ID_RE.fullmatch(value):
        raise CcaError("HetrixTools API returned a monitor with an invalid id")
    return value


def label(monitor: dict) -> str:
    text = f"{monitor.get('name', '?')} [{monitor.get('type', '?')}]"
    state = monitor.get("monitor_status")
    if isinstance(state, str) and state != "active":
        text += f" ({state})"
    return text


def is_down(monitor: dict) -> bool:
    return monitor.get("uptime_status") == "down"


def status(api: Api, _args: argparse.Namespace) -> int:
    down = monitors(api, uptime_status="down")
    if not down:
        print("All monitors are UP")
        return 0
    print(f"{len(down)} monitor(s) DOWN:")
    for m in sorted(down, key=lambda m: str(m.get("name"))):
        print(f"  {label(m)}")
    return 1


def show_down(api: Api, _args: argparse.Namespace) -> int:
    down = monitors(api, uptime_status="down")
    print("DOWN monitors:")
    if not down:
        print("  (none)")
    for m in sorted(down, key=lambda m: str(m.get("name"))):
        since = local_time(m.get("last_status_change"))
        print(f"  {label(m)}: DOWN since {since} - {m.get('target')}")
    return 0


def show_all(api: Api, _args: argparse.Namespace) -> int:
    everything = sorted(monitors(api), key=lambda m: str(m.get("name")))
    t = now()
    print("UP monitors:")
    up = [m for m in everything if not is_down(m)]
    if not up:
        print("  (none)")
    for m in up:
        changed = m.get("last_status_change")
        for_text = f"UP for {duration(t - changed)}" if isinstance(changed, int) else "UP"
        print(f"  {label(m)}: {for_text} ({m.get('uptime')}% uptime)")
    print()
    print("DOWN monitors:")
    down = [m for m in everything if is_down(m)]
    if not down:
        print("  (none)")
    for m in down:
        print(f"  {label(m)}: DOWN since {local_time(m.get('last_status_change'))}")
    return 0


def locations(monitor: dict) -> list[tuple[str, int]]:
    """(location, response time ms); the API returns a map or a list of maps per location."""
    raw = monitor.get("locations")
    maps = raw if isinstance(raw, list) else [raw]
    result = []
    for entry in maps:
        if not isinstance(entry, dict):
            continue
        for name, value in entry.items():
            checks = value if isinstance(value, list) else [value]
            for check in checks:
                if isinstance(check, dict) and isinstance(check.get("response_time"), int):
                    result.append((name, check["response_time"]))
    return sorted(result)


def show_response_times(api: Api, _args: argparse.Namespace) -> int:
    print("Response times of UP monitors:")
    shown = 0
    for m in sorted(monitors(api, uptime_status="up"), key=lambda m: str(m.get("name"))):
        times = locations(m)
        if not times:
            continue
        shown += 1
        print(f"  {label(m)} ({m.get('uptime')}% uptime):")
        for name, ms in times:
            mark = " very slow" if ms > VERY_SLOW_MS else " slow" if ms > SLOW_MS else ""
            print(f"    {name}: {ms} ms{mark}")
    if not shown:
        print("  (none)")
    return 0


def show_outages(api: Api, args: argparse.Namespace) -> int:
    since, until, period = window(args, 86400, "last 24 hours")
    t = now()
    changed = [
        m
        for m in monitors(api)
        if isinstance(m.get("last_status_change"), int)
        and since <= m["last_status_change"] <= until
    ]
    print(f"Status changes {period}:")
    if not changed:
        print("  (none)")
    for m in sorted(changed, key=lambda m: m["last_status_change"], reverse=True):
        ts = m["last_status_change"]
        current = str(m.get("uptime_status", "unknown")).upper()
        print(f"  {label(m)}: changed {local_time(ts)} ({duration(t - ts)} ago), now {current}")
    print()
    print("Only the last status change of each monitor is known here;")
    print("use monitor-outages MONITOR for the failures of one monitor.")
    return 0


def show_monitor_info(api: Api, args: argparse.Namespace) -> int:
    m = find_monitor(api, args.monitor)
    print("Monitor:")
    print(f"  Name:     {m.get('name')}")
    print(f"  Type:     {m.get('type')}")
    print(f"  Status:   {str(m.get('uptime_status', 'unknown')).upper()}")
    print(f"  Monitor:  {m.get('monitor_status')}")
    print(f"  Uptime:   {m.get('uptime')}%")
    print(f"  Target:   {m.get('target')}")
    print(f"  Category: {m.get('category')}")
    print(f"  ID:       {monitor_id(m)}")
    return 0


# --- location fail log


def fail_log(api: Api, mid: str, since: int, until: int) -> tuple[list[dict], bool]:
    """Failures in [since, until] oldest first, and whether the page limit cut them off.

    The API scans backwards from `timestamp` over `minutes` minutes that have failures;
    meta.next_page_timestamp continues the scan.
    """
    entries: dict[tuple, dict] = {}
    cursor = until
    for _page in range(FAIL_LOG_PAGES):
        data = api.get(
            f"/uptime-monitors/{mid}/location-fail-log",
            {"timestamp": cursor, "minutes": FAIL_LOG_MINUTES},
        )
        batch = data.get("entries")
        for e in batch if isinstance(batch, list) else []:
            if not isinstance(e, dict) or not isinstance(e.get("timestamp"), int):
                continue
            entry = {
                "timestamp": e["timestamp"],
                "location": str(e.get("location", "?")),
                "data": str(e.get("data", "")),
            }
            if since <= entry["timestamp"] <= until:
                entries[(entry["timestamp"], entry["location"], entry["data"])] = entry
        meta = data.get("meta")
        following = meta.get("next_page_timestamp") if isinstance(meta, dict) else None
        if not isinstance(following, int) or following < since or following >= cursor:
            return sorted(entries.values(), key=lambda e: (e["timestamp"], e["location"])), False
        cursor = following
    return sorted(entries.values(), key=lambda e: (e["timestamp"], e["location"])), True


def signature(message: str) -> str:
    for pattern in SIGNATURE_SUBS:
        message = pattern.sub("", message)
    return message


def outage_windows(entries: list[dict], gap: int) -> list[list[dict]]:
    """Entries (oldest first) split where two failures are more than `gap` seconds apart."""
    windows: list[list[dict]] = []
    for e in entries:
        if windows and e["timestamp"] - windows[-1][-1]["timestamp"] <= gap:
            windows[-1].append(e)
        else:
            windows.append([e])
    return windows


def plural(count: int, word: str, many: str | None = None) -> str:
    return f"{count} {word if count == 1 else many or word + 's'}"


def window_time(first: int, last: int) -> str:
    start, end = local_time(first), local_time(last)
    if start == end:
        return start
    if time.strftime("%F", time.localtime(first)) == time.strftime("%F", time.localtime(last)):
        date_hm, zone = start.rsplit(" ", 1)  # 2026-08-21 09:55-09:56 CEST
        return f"{date_hm}-{time.strftime('%H:%M', time.localtime(last))} {zone}"
    return f"{start} - {end}"


def show_monitor_outages(api: Api, args: argparse.Namespace) -> int:
    if args.gap < 0:
        raise CcaError("--gap must not be negative")
    since, until, period = window(args, 7 * 86400, "last 7 days")
    m = find_monitor(api, args.monitor)
    mid = monitor_id(m)
    print(f"Outage history: {label(m)} ({mid})")
    print(f"Period: {period}")
    print()
    entries, truncated = fail_log(api, mid, since, until)
    if not entries:
        print("No failures in this period")
        return 0
    if truncated:
        print(f"Warning: stopped after {FAIL_LOG_PAGES} pages, older failures are missing")
        print("(narrow the period with --since/--until)")
        print()
    if args.full:
        print(f"Failures ({plural(len(entries), 'entry', 'entries')}):")
        for e in entries:
            print(f"  {local_time(e['timestamp'])} [{e['location']}]: {e['data']}")
    else:
        windows = outage_windows(entries, args.gap)
        print(
            f"Failures ({plural(len(entries), 'entry', 'entries')}"
            f" in {plural(len(windows), 'outage window')}):"
        )
        for w in windows:
            counts: dict[str, int] = {}
            for e in w:
                key = signature(e["data"])
                counts[key] = counts.get(key, 0) + 1
            errors = ", ".join(
                f"{n}x {err}" for err, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            )
            places = sorted({e["location"] for e in w})
            when = window_time(w[0]["timestamp"], w[-1]["timestamp"])
            print(f"  {when} | {plural(len(w), 'entry', 'entries')} | {errors}")
            print(f"      {plural(len(places), 'location')}: {', '.join(places)}")
    print()
    print("Summary:")
    print(f"  Failure times: {len({e['timestamp'] for e in entries})}")
    print(f"  Locations: {len({e['location'] for e in entries})}")
    oldest, newest = entries[0]["timestamp"], entries[-1]["timestamp"]
    print(f"  First and last failure: {local_time(oldest)} -> {local_time(newest)}")
    return 0


# --- server agent


def iec(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    size = float(value)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def number(value: Any, suffix: str = "") -> str:
    return f"{value:g}{suffix}" if isinstance(value, (int, float)) else "?"


def show_server_stats(api: Api, args: argparse.Namespace) -> int:
    m = find_monitor(api, args.monitor)
    data = api.get(f"/uptime-monitors/{monitor_id(m)}/server-agent/metrics")
    agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
    system = data.get("system") if isinstance(data.get("system"), dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    print(f"Server stats: {m.get('name')}")
    print(f"  Host:    {system.get('hostname')}, {system.get('operating_system')}, kernel"
          f" {system.get('kernel')}")  # fmt: skip
    reboot = system.get("reboot_required")
    print(f"  Reboot required: {'yes' if reboot else 'no' if reboot is False else '?'}")
    uptime = system.get("uptime")
    print(f"  Uptime:  {uptime // 86400 if isinstance(uptime, int) else '?'} days")
    print(f"  Agent:   {agent.get('version')} [{agent.get('type')}],"
          f" last data {local_time(meta.get('last_updated'))}")  # fmt: skip
    stats = data.get("stats")
    latest = stats[0] if isinstance(stats, list) and stats and isinstance(stats[0], dict) else {}
    if latest:
        loads = "/".join(number(latest.get(k)) for k in ("load_1", "load_5", "load_15"))
        print(f"  Now:     CPU {number(latest.get('cpu'), '%')}, RAM"
              f" {number(latest.get('ram'), '%')}, load {loads}")  # fmt: skip
    disk = data.get("disk") if isinstance(data.get("disk"), dict) else {}
    disks = [d for d in disk.get("disks") or [] if isinstance(d, dict)]
    print("  Disks:")
    if not disks:
        print("    (none reported)")
    for d in disks:
        pct = d.get("usage_percent")
        if not isinstance(pct, (int, float)):
            size, used = d.get("size"), d.get("used")
            ok = isinstance(size, (int, float)) and isinstance(used, (int, float)) and size > 0
            pct = used * 100 / size if ok else None
        flag = ""
        if isinstance(pct, (int, float)):
            flag = (
                " CRITICAL" if pct >= DISK_CRITICAL else " WARNING" if pct >= DISK_WARNING else ""
            )
        shown = f"{pct:.1f}" if isinstance(pct, (int, float)) else "?"
        print(f"    {str(d.get('mount')):<24} {shown:>5}% used"
              f" ({iec(d.get('available'))} free of {iec(d.get('size'))}){flag}")  # fmt: skip
    for d in disks:
        raid = d.get("raid")
        if isinstance(raid, dict):
            print(f"  RAID {d.get('mount')}: {raid.get('type')} {raid.get('health')}"
                  f" {raid.get('state')} ({raid.get('active_drives')}/{raid.get('total_drives')}"
                  f" active, {raid.get('failed_drives')} failed)")  # fmt: skip
    return 0


# --- blacklist monitors


def rbls(monitor: dict) -> list[dict]:
    listed = monitor.get("listed")
    return [r for r in listed if isinstance(r, dict)] if isinstance(listed, list) else []


def is_warning(rbl: dict) -> bool:
    return str(rbl.get("rbl", "")).lower() in WARN_RBLS


def show_blacklist(api: Api, args: argparse.Namespace) -> int:
    if args.target is not None:
        return show_blacklist_target(api, args.target)
    listed = [m for m in api.pages("/blacklist-monitors", "monitors", {"listed": "true"}, 1024)
              if rbls(m)]  # fmt: skip
    print("Blacklist status:")
    if not listed:
        print("  No monitored target is listed")
        return 0
    failing = False
    for m in sorted(listed, key=lambda m: str(m.get("name"))):
        names = []
        for r in rbls(m):
            names.append(f"{r.get('rbl')}{' (warning)' if is_warning(r) else ''}")
            failing = failing or not is_warning(r)
        count = plural(len(names), "blacklist")
        print(f"  {m.get('name')} ({m.get('target')}): {count}: {', '.join(names)}")
    print()
    print("(warning): dnsbl-2/dnsbl-3.uceprotect.net listings do not fail the check")
    print("Details and delist links: blacklist TARGET")
    return 1 if failing else 0


def show_blacklist_target(api: Api, target: str) -> int:
    if not TARGET_RE.fullmatch(target):
        raise CcaError(f"invalid target '{validate.display(target)}' (IPv4 address or domain)")
    found = api.pages(
        "/blacklist-monitors", "monitors", {"target": target, "exact_target": "true"}, 1024
    )
    if not found:
        raise CcaError(f"no blacklist monitor for {target}", code=1)
    failing = False
    for m in found:
        listed = rbls(m)
        if not listed:
            print(f"{m.get('name')} ({m.get('target')}) is not on any blacklist")
            continue
        print(f"{m.get('name')} ({m.get('target')}) is on {plural(len(listed), 'blacklist')}:")
        for r in listed:
            note = " (warning only)" if is_warning(r) else ""
            print(f"  {r.get('rbl')}{note}")
            print(f"      delist: {r.get('delist')}")
            failing = failing or not is_warning(r)
    return 1 if failing else 0


# --- command line

COMMANDS = {
    "status": status,
    "down": show_down,
    "all": show_all,
    "response-times": show_response_times,
    "outages": show_outages,
    "monitor-outages": show_monitor_outages,
    "monitor-info": show_monitor_info,
    "server-stats": show_server_stats,
    "blacklist": show_blacklist,
}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.description = "HetrixTools uptime monitors, outages, server agent stats, blacklists."
    parser.epilog = EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.set_defaults(hetrix_help=parser.format_help)
    sub = parser.add_subparsers(dest="hetrix_command", metavar="COMMAND")

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, description=help_text)

    def period(p: argparse.ArgumentParser, default: str) -> None:
        p.add_argument("--since", type=parse_time, help=f"start (default: {default})")
        p.add_argument("--until", type=parse_time, help="end (default: now)")

    command("status", "exit 0 when every monitor is UP, 1 when any is DOWN")
    command("down", "DOWN monitors with the time they went down and their target")
    command("all", "every monitor: UP with duration and uptime, DOWN with since")
    command("response-times", "response time per location of UP monitors")
    p = command("outages", "monitors whose status changed in a period")
    period(p, "24 hours ago")
    p = command("monitor-outages", "failures of one monitor grouped into outage windows")
    p.add_argument("monitor", metavar="MONITOR")
    period(p, "7 days ago")
    p.add_argument("--full", action="store_true", help="one line per failure")
    p.add_argument(
        "--gap", type=int, default=900, help="seconds between two outage windows (default: 900)"
    )
    p = command("monitor-info", "details of one monitor including its target")
    p.add_argument("monitor", metavar="MONITOR")
    p = command("server-stats", "server agent data of a monitor: system, load, disks, RAID")
    p.add_argument("monitor", metavar="MONITOR")
    p = command("blacklist", "listed targets, or the blacklists of one TARGET")
    p.add_argument("target", metavar="TARGET", nargs="?", help="IPv4 address or domain")


def run(args: argparse.Namespace) -> int:
    if args.hetrix_command is None:
        print(args.hetrix_help(), file=sys.stderr, end="")
        return 2
    return COMMANDS[args.hetrix_command](connect(args), args)
