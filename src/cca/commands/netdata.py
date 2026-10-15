"""cca netdata: query a Netdata agent directly or over ssh (doc-4)."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import math
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cca import config, ssh, validate
from cca.output import CcaError

DEFAULT_PORT = 19999
TIMEOUT = 10  # curl --max-time, socket timeout
SLACK = 15  # added for the whole fetch (ssh connection, slow responses)
ALL_TIMEOUT = 12  # per server in `fping --all`
HISTORY_AFTER = -7776000  # 90 days
DEFAULT_CACHE_DIR = "server-logs/fping"  # without a .cca.toml: from the CWD
MAX_BODY = 64 * 1024 * 1024  # API response cap (a 90-day fping history is a few MB)

STATS_KEYWORDS = ["load", "cpu", "disk", "net", "ram", "mem", "req", "bytes"]
TOP_SKIP_WORDS = [
    "time", "date", "anomaly", "free", "used", "allocated", "available", "size", "cache",
    "heap", "list", "thread", "central", "page", "dbengine", "metadata", "sqlite3",
    "buffer", "aral", "judy", "uuid", "ml", "success", "error", "remote", "local",
    "online", "active", "console", "graphical", "power", "passed", "failed",
    "temperature", "inactive", "cpu", "activating", "deactivating", "closing", "strings",
    "avail", "streaming", "current", "labels", "dirty", "speed", "slots", "demand",
    "health log",
]  # fmt: skip
DISCOVER_KEYWORDS = {
    "load": ["system.load", "system.cpu"],
    "cpu": ["system.cpu", "app.cpu"],
    "memory": ["system.ram", "system.swap", "mem.available"],
    "disk": ["disk.io", "disk.space", "disk.ops"],
    "network": ["net.", "system.net"],
    "web": ["web_log", "apache", "nginx"],
    "request": ["web_log.requests", "web_log.requests_by_vhost"],
    "vhost": ["web_log.requests_by_vhost"],
    "top": ["web_log.requests_by_vhost"],
}
_BASENAME_RE = re.compile(r"[a-z0-9._+-]{1,200}")  # doc-2 "Generated file names"

EPILOG = """\
examples:
  cca netdata --server server1 list
  cca netdata --server server1 list --pattern nginx
  cca netdata --server server1 meta --context system.cpu
  cca netdata --server server1 discover "load spikes"
  cca netdata --server server1 query --context system.cpu --after -300
  cca netdata --server server1 stats --context system.load --after -86400
  cca netdata --server server1 top --context apache.workers --after "today 10:30"
  cca netdata --server server1 fping --per-target
  cca netdata fping --all
  cca netdata --server server1 fping --history --target example.com

Times (--after/--before, UTC): -SECONDS (relative), HH:MM, "today HH[:MM]",
"yesterday HH[:MM]", YYYY-MM-DD, "YYYY-MM-DD HH:MM[:SS]".
"""


class FetchError(CcaError):
    """The Netdata API could not be read (exit 1); `fping --all` reports it per server."""

    def __init__(self, message: str):
        super().__init__(message, code=1)


# --- argument types (errors are usage errors, exit 2)


def parse_time(value: str, now: datetime | None = None) -> int:
    """Relative seconds (negative) or a Unix timestamp; absolute forms are UTC."""
    text = value.strip()
    if re.fullmatch(r"-[0-9]+", text):
        return int(text)
    now = now or datetime.now(UTC)
    lower = text.lower()
    try:
        for word, days in (("today ", 0), ("yesterday ", 1)):
            if lower.startswith(word):
                m = re.fullmatch(r"([0-9]{1,2})(?::([0-9]{2}))?", text[len(word) :].strip())
                if m:
                    day = datetime(now.year, now.month, now.day, tzinfo=UTC)
                    hour, minute = int(m[1]), int(m[2] or 0)
                    return int(
                        (day.replace(hour=hour, minute=minute) - timedelta(days=days)).timestamp()
                    )
                raise ValueError
        m = re.fullmatch(r"([0-9]{1,2}):([0-9]{2})", text)
        if m:
            day = datetime(now.year, now.month, now.day, tzinfo=UTC)
            return int(day.replace(hour=int(m[1]), minute=int(m[2])).timestamp())
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return int(parsed.replace(tzinfo=UTC).timestamp())
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(
        f"invalid time '{validate.display(value)}' (see `cca netdata --help`)"
    )


def _int_range(low: int, high: int | None = None):
    def check(value: str) -> int:
        if value.isascii() and value.isdigit():
            number = int(value)
            if number >= low and (high is None or number <= high):
                return number
        bound = f"{low}-{high}" if high is not None else f">= {low}"
        raise argparse.ArgumentTypeError(f"invalid value '{validate.display(value)}' ({bound})")

    return check


def _threshold(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        number = math.nan
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(f"invalid threshold '{validate.display(value)}' (ms > 0)")
    return number


def _hours(value: str) -> set[int]:
    hour = _int_range(0, 23)
    try:
        return {hour(part.strip()) for part in value.split(",")}
    except argparse.ArgumentTypeError:
        raise argparse.ArgumentTypeError(
            f"invalid hours '{validate.display(value)}' (comma-separated UTC hours 0-23)"
        ) from None


def _host(value: str) -> str:
    host = None if "%" in value else validate.host(value)
    if host is None:
        raise argparse.ArgumentTypeError(
            f"invalid host '{validate.display(value)}' (expected a DNS name, IPv4 or IPv6)"
        )
    return host


def _target(value: str) -> str:
    if len(value) > validate.NAME_MAX or not validate.FPING_TARGET_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"invalid target '{validate.display(value)}' "
            "(expected [A-Za-z0-9][A-Za-z0-9._-]*, max 64)"
        )
    return value


# --- parser


def _connection(parser: argparse.ArgumentParser) -> None:
    """Connection options; accepted before and after COMMAND (SUPPRESS keeps either)."""
    group = parser.add_argument_group("connection")
    group.add_argument(
        "--server",
        metavar="NAME",
        default=argparse.SUPPRESS,
        help="server from [servers] in .cca.toml",
    )
    group.add_argument(
        "--host",
        type=_host,
        default=argparse.SUPPRESS,
        help="Netdata host without --server (default: localhost, direct transport)",
    )
    group.add_argument(
        "--port",
        type=_int_range(1, 65535),
        default=argparse.SUPPRESS,
        help="with --host (default: 19999)",
    )
    group.add_argument(
        "--transport",
        choices=("ssh", "direct"),
        default=argparse.SUPPRESS,
        help="with --server: curl on the server over ssh, or HTTP from here "
        "(default: servers.NAME.netdata_transport)",
    )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.description = "Query the Netdata API of a server, over ssh or directly."
    parser.epilog = EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.set_defaults(netdata_help=parser.format_help)
    _connection(parser)
    sub = parser.add_subparsers(dest="netdata_command", metavar="COMMAND")

    def command(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        _connection(p)
        return p

    def window(p: argparse.ArgumentParser, after: int | None) -> None:
        shown = "-900, -7776000 with --history" if after is None else str(after)
        p.add_argument("--after", type=parse_time, default=after, help=f"start (default: {shown})")
        p.add_argument("--before", type=parse_time, help="end (default: now)")

    p = command("list", "metric groups, or charts whose id contains --pattern")
    p.add_argument("--pattern", help="case-insensitive substring of the chart id")

    p = command("query", "raw v3/data JSON of a context")
    p.add_argument("--context", required=True, help="for example system.cpu")
    window(p, -300)

    aggregation = {"choices": ("min", "max", "avg"), "default": "max", "help": "default: max"}
    points = {"type": _int_range(1, 1000), "default": 24, "help": "intervals, 1-1000 (default: 24)"}

    p = command("stats", "aggregated values of a context per interval")
    p.add_argument("--context", required=True, help="for example system.load")
    window(p, -3600)
    p.add_argument("--aggregation", **aggregation)
    p.add_argument("--points", **points)
    p.add_argument("--instance", help="one instance (default: all summed)")
    p.add_argument("--dimension", help="one dimension (default: picked by keyword)")

    p = command("top", "top N labels of a context (domains first)")
    p.add_argument("--context", required=True, help="for example web_log.requests_by_vhost")
    window(p, -3600)
    p.add_argument("-n", "--n", type=_int_range(1), default=20, help="rows (default: 20)")
    p.add_argument("--aggregation", **aggregation)
    p.add_argument("--points", **points)
    p.add_argument(
        "--group-by",
        choices=("dimension", "instance", "label", "node"),
        default="dimension",
        help="default: dimension; instance for app.* contexts",
    )

    p = command("fping", "network latency and packet loss from the fping plugin")
    window(p, None)
    p.add_argument(
        "--threshold", type=_threshold, default=100.0, help="latency threshold in ms (default: 100)"
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--per-target", action="store_true", help="latency per target (localization)")
    mode.add_argument(
        "--history", action="store_true", help="event trend over time (cached series)"
    )
    p.add_argument("--all", action="store_true", help="every [servers] entry with netdata_host")
    p.add_argument(
        "--target",
        type=_target,
        help="--history: targets containing this (default: netdata.fping_target)",
    )
    p.add_argument(
        "--min-seconds",
        type=_int_range(0),
        default=60,
        help="--history: minimum event length (default: 60)",
    )
    p.add_argument(
        "--cache",
        metavar="PATH",
        help="--history: series file (default: in netdata.fping_cache_dir)",
    )
    p.add_argument(
        "--refresh", action="store_true", help="--history: fetch again instead of reading the cache"
    )
    p.add_argument(
        "--exclude-hours", type=_hours, metavar="H[,H...]", help="--history: skip these UTC hours"
    )

    p = command("discover", "suggest contexts for a question")
    p.add_argument("question", metavar="QUESTION")

    p = command("meta", "charts, dimensions and sample labels of a context")
    p.add_argument("--context", required=True, help="for example system.cpu")


# --- API access


class Netdata:
    def __init__(self, host: str, port: int, destination: str | None = None,
                 server: str | None = None, timeout: int | None = None):  # fmt: skip
        self.host = host  # normalized (validate.host)
        self.port = port
        self.destination = destination  # ssh destination: curl runs on the server
        self.server = server
        self.timeout = timeout or TIMEOUT

    def address(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    def url(self, api: str, endpoint: str, params: dict[str, Any] | None = None) -> str:
        query = "?" + urllib.parse.urlencode(params) if params else ""
        return f"http://{self.address()}/api/{api}{endpoint}{query}"

    def fetch(self, api: str, endpoint: str, params: dict[str, Any] | None = None,
              clean: bool = True) -> Any:  # fmt: skip
        """Parsed JSON; with `clean`, strings are escaped for printing (raw for `query`)."""
        url = self.url(api, endpoint, params)
        body = self._ssh(url) if self.destination else self._direct(url)
        if len(body) > MAX_BODY:
            raise FetchError(f"fetching {url}: response larger than {MAX_BODY} bytes")
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError as e:  # includes UnicodeDecodeError
            raise FetchError(f"fetching {url}: invalid JSON ({e})") from None
        return _clean(data) if clean else data

    def _direct(self, url: str) -> bytes:
        """HTTP GET in a worker thread: the deadline also covers slow headers and a
        trickled body (the socket timeout only bounds each read)."""
        outcome: list = []
        worker = threading.Thread(target=self._direct_read, args=(url, outcome), daemon=True)
        worker.start()
        worker.join(self.timeout + SLACK)
        if not outcome:  # still running: abandoned, it stops at the cap or socket timeout
            raise FetchError(f"fetching {url}: timed out")
        if isinstance(outcome[0], FetchError):
            raise outcome[0]
        return outcome[0]

    def _direct_read(self, url: str, outcome: list) -> None:
        # no proxy from the environment: the agent is on a private (VPN) address
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body = bytearray()
        try:
            with opener.open(url, timeout=self.timeout) as response:
                while len(body) <= MAX_BODY:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    body += chunk
        except (OSError, http.client.HTTPException) as e:
            outcome.append(FetchError(f"fetching {url}: {validate.display(str(e))}"))
            return
        outcome.append(bytes(body))

    def _ssh(self, url: str) -> bytes:
        if shutil.which("ssh") is None:
            raise CcaError("ssh not found on PATH")
        curl = ["curl", "-fsS", "--max-time", str(self.timeout), url]
        argv = ssh.argv(self.destination, shlex.join(curl))
        out, err = bytearray(), bytearray()
        overflow = threading.Event()

        def pump(stream, buf: bytearray, limit: int, kill: bool) -> None:
            while chunk := stream.read1(65536):
                if len(buf) + len(chunk) > limit:
                    if kill:  # stdout over the cap: stop the child
                        overflow.set()
                        return
                    buf += chunk[: max(0, limit - len(buf))]  # stderr: keep the first part
                    continue  # and keep draining
                buf += chunk

        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        pumps = [
            threading.Thread(target=pump, args=(proc.stdout, out, MAX_BODY, True), daemon=True),
            threading.Thread(target=pump, args=(proc.stderr, err, 4096, False), daemon=True),
        ]
        for t in pumps:
            t.start()
        deadline = time.monotonic() + self.timeout + SLACK
        while proc.poll() is None and not overflow.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)
        code = proc.poll()
        if code is None:
            proc.kill()
            proc.wait()
        pumps[0].join(self.timeout)  # the rest of stdout after the exit
        pumps[1].join(1)  # stderr may stay open in a backgrounded ssh control master
        if overflow.is_set():
            raise FetchError(f"fetching {url}: response larger than {MAX_BODY} bytes")
        if code is None:
            raise FetchError(f"fetching {url}: ssh to {self.server} timed out")
        if code == 255:
            raise FetchError(f"fetching {url}: ssh to {self.server} failed (exit 255)")
        if code == 127:
            raise FetchError(f"fetching {url}: curl not found on {self.server}")
        if code != 0:
            detail = err.decode("utf-8", "replace").strip() or f"curl exit {code}"
            raise FetchError(f"fetching {url} on {self.server}: {validate.display(detail)}")
        return bytes(out)

    def charts(self) -> dict[str, Any]:
        data = self.fetch("v1", "/charts")
        charts = data.get("charts") if isinstance(data, dict) else None
        return charts if isinstance(charts, dict) else {}

    def data(self, context: str, after: int, before: int | None = None, clean: bool = True,
             **extra: Any) -> Any:  # fmt: skip
        params: dict[str, Any] = {"scope_contexts": context, "after": str(after)}
        if before is not None:
            params["before"] = str(before)
        params.update({k: str(v) for k, v in extra.items() if v is not None})
        params["format"] = "json"
        return self.fetch("v3", "/data", params, clean)


def _clean(value: Any) -> Any:
    """API JSON with every string made safe for the terminal (control characters escaped)."""
    if isinstance(value, str):
        return validate.display(value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {validate.display(k): _clean(v) for k, v in value.items()}
    return value


def _result(data: Any) -> tuple[dict, list, list]:
    """(result, labels, rows) of a v3/data answer; empty when the shape is unexpected."""
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return {}, [], []
    labels, rows = result.get("labels"), result.get("data")
    labels = [str(x) for x in labels] if isinstance(labels, list) else []
    rows = [r for r in rows if isinstance(r, list) and r] if isinstance(rows, list) else []
    return result, labels, rows


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _hms(ts: float | None) -> str:
    return "-" if ts is None else datetime.fromtimestamp(ts, tz=UTC).strftime("%H:%M:%S")


def _median_low(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


# --- commands


def cmd_list(nd: Netdata, args: argparse.Namespace) -> int:
    charts = nd.charts()
    if args.pattern is None:
        groups: dict[str, int] = {}
        for chart in charts.values():
            context = str(chart.get("context", "")) if isinstance(chart, dict) else ""
            prefix = context.split(".")[0] if "." in context else "other"
            groups[prefix] = groups.get(prefix, 0) + 1
        print("=== Metric groups ===")
        for prefix, count in sorted(groups.items(), key=lambda g: g[1], reverse=True)[:15]:
            print(f"  {prefix:20s} {count:4d} charts")
        print(f"\nTotal: {len(charts)} charts")
        print("\nUsage:")
        print("  list --pattern nginx            # charts whose id contains nginx")
        print("  meta --context system.cpu       # details of one context")
        return 0
    matched = {k: v for k, v in charts.items() if args.pattern.lower() in k.lower()}
    if not matched:
        print(f"No charts match pattern: {args.pattern}")
        return 0
    print(f"{'Chart ID':50s} {'Title':60s} Context")
    print("-" * 140)
    for chart_id, chart in sorted(matched.items()):
        chart = chart if isinstance(chart, dict) else {}
        title = str(chart.get("title", "N/A"))[:60]
        context = str(chart.get("context", "N/A"))[:30]
        print(f"{chart_id:50s} {title:60s} {context}")
    return 0


def cmd_query(nd: Netdata, args: argparse.Namespace) -> int:
    # json.dumps escapes control characters itself
    print(json.dumps(nd.data(args.context, args.after, args.before, clean=False), indent=2))
    return 0


def cmd_stats(nd: Netdata, args: argparse.Namespace) -> int:
    data = nd.data(
        args.context, args.after, args.before, time_group=args.aggregation, points=args.points,
        instances=args.instance, dimensions=args.dimension,
    )  # fmt: skip
    result, labels, rows = _result(data)
    if not result:
        print("No data")
        return 0
    if not rows:
        print("No rows")
        return 0
    if args.dimension:  # show everything the API returned for an explicit dimension
        columns = list(enumerate(labels[1:], 1))
    else:
        columns = [
            (i, label)
            for i, label in enumerate(labels[1:], 1)
            if any(kw in label.lower() for kw in STATS_KEYWORDS) and len(label) < 40
        ]
    if not columns:
        if len(labels) < 2:
            print("No relevant labels")
            return 0
        columns = [(1, labels[1])]
    header = f"{'Time (UTC)':16s} | " + " | ".join(f"{label[:15]:15s}" for _, label in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        values = [datetime.fromtimestamp(row[0], tz=UTC).strftime("%Y-%m-%d %H:%M")]
        for idx, _ in columns:
            if idx >= len(row):
                values.append("     N/A")
            elif isinstance(row[idx], float):
                values.append(f"{row[idx]:8.2f}")
            else:
                values.append(f"{row[idx]!s:8s}")
        print(" | ".join(values))
    return 0


def cmd_top(nd: Netdata, args: argparse.Namespace) -> int:
    data = nd.data(
        args.context, args.after, args.before, time_group=args.aggregation, points=args.points,
        group_by=args.group_by,
    )  # fmt: skip
    result, labels, rows = _result(data)
    if not result:
        print("No data")
        return 0
    if not rows:
        print("No rows")
        return 0
    domains, metrics = [], []
    for i, label in enumerate(labels[1:], 1):
        if args.group_by == "instance":  # columns are instances: keep them all
            metrics.append((i, label))
        elif label.count(".") >= 2 and 3 < len(label) < 60:
            domains.append((i, label))
        elif len(label) < 40 and not any(w in label.lower() for w in TOP_SKIP_WORDS):
            metrics.append((i, label))
    if not domains and not metrics:
        print("No relevant columns found")
        return 0

    def totals(columns: list[tuple[int, str]]) -> dict[str, tuple[float, int]]:
        out = {}
        for idx, label in columns:
            values = [r[idx] for r in rows if idx < len(r) and _number(r[idx])]
            if sum(values) > 0:
                out[label] = (sum(values), len(values))
        return out

    domain_totals, metric_totals = totals(domains), totals(metrics)
    ranked = sorted(domain_totals.items(), key=lambda x: x[1][0], reverse=True)
    ranked += sorted(metric_totals.items(), key=lambda x: x[1][0], reverse=True)
    shown = ranked[: args.n]
    print(f"=== TOP {len(shown)} (context: {args.context}) ===")
    print(f"  Domains: {len(domain_totals)}, metrics: {len(metric_totals)}")
    print(f"{'Rank':>4} | {'Label':40s} | {'Total':>12} | {'Avg':>10}")
    print("-" * 75)
    for rank, (label, (total, count)) in enumerate(shown, 1):
        avg = total / count if count else 0
        cut = label if len(label) <= 40 else label[:37] + "..."
        marker = "*" if label in domain_totals else " "
        print(f"{rank:4d} {marker}| {cut:40s} | {total:12.0f} | {avg:10.2f}")
    print("  * = domain")
    return 0


def cmd_discover(nd: Netdata, args: argparse.Namespace) -> int:
    charts = [c for c in nd.charts().values() if isinstance(c, dict)]
    question = args.question.lower()
    matched = {ctx for kw, ctxs in DISCOVER_KEYWORDS.items() if kw in question for ctx in ctxs}
    for chart in charts:
        context = str(chart.get("context", ""))
        title = str(chart.get("title", "")).lower()
        if context and any(part and part in question for part in (context.split(".")[0], title)):
            matched.add(context)
    if not matched:
        print("No matching metrics found.")
        print("Try: list [--pattern TEXT] for an overview")
        return 0
    print("=== Suggested metrics ===")
    for context in sorted(matched):
        chart = next((c for c in charts if c.get("context") == context), None)
        if chart:
            print(f"\n{context}")
            print(f"  Title: {chart.get('title', 'N/A')}")
            print(f"  Units: {chart.get('units', '')}")
            print(f"  Usage: stats --context {context} --after -3600")
    return 0


def cmd_meta(nd: Netdata, args: argparse.Namespace) -> int:
    matching = [
        (chart_id, chart)
        for chart_id, chart in nd.charts().items()
        if isinstance(chart, dict) and chart.get("context") == args.context
    ]
    if not matching:
        print(f"Context '{args.context}' not found")
        print("Use 'list' for an overview of the available metrics")
        return 0
    for chart_id, chart in matching:
        print(f"=== Chart: {chart_id} ===")
        print(f"Title:       {chart.get('title', 'N/A')}")
        print(f"Context:     {chart.get('context', 'N/A')}")
        print(f"Units:       {chart.get('units', 'N/A')}")
        print(f"Family:      {chart.get('family', 'N/A')}")
        print(f"Type:        {chart.get('chart_type', 'N/A')}")
        dims = chart.get("dimensions")
        dims = dims if isinstance(dims, dict) else {}
        print(f"\nDimensions ({len(dims)}):")
        for name, info in list(dims.items())[:10]:
            shown = info.get("name", name) if isinstance(info, dict) else name
            print(f"  - {name}: {shown}")
        if len(dims) > 10:
            print(f"  ... and {len(dims) - 10} more")
        print("\nSample data (5 points):")
        # v3 has no `context=`: scope to the context and this chart
        result, labels, _ = _result(nd.data(args.context, -300, instances=chart_id, points=5))
        if result:
            print(f"Labels ({len(labels)}):")
            for i, label in enumerate(labels[:15]):
                print(f"  [{i}] {label}")
            if len(labels) > 15:
                print(f"  ... and {len(labels) - 15} more")
        print("\nUsage:")
        print(f"  stats --context {args.context} --after -3600")
        print(f"  query --context {args.context} --after -300")
    return 0


# --- fping


def fping_loss(nd: Netdata, after: int, before: int | None) -> dict | None:
    """Packet loss from fping.quality (100 = no loss); None when there was none.

    A full outage returns no latency samples at all, so only this catches it.
    """
    _, labels, rows = _result(nd.data("fping.quality", after, before, group_by="instance"))
    if not rows or len(labels) < 2:
        return None
    buckets = []  # (ts, worst quality, affected targets)
    for r in rows:
        values = [(labels[i], r[i]) for i in range(1, len(labels)) if i < len(r) and _number(r[i])]
        if values:
            buckets.append((r[0], min(v for _, v in values), [n for n, v in values if v < 100]))
    bad = sorted((b for b in buckets if b[1] < 100), key=lambda b: b[0])
    if not bad:
        return None
    stamps = sorted(b[0] for b in buckets)
    step = min((b - a for a, b in zip(stamps, stamps[1:])), default=0)
    worst_ts, worst_q, _ = min(bad, key=lambda b: b[1])
    # window = the contiguous run around the worst bucket, not the span of all dips
    run = [b for b in bad if b[0] == worst_ts]
    gap = max(step * 2, 1)
    for b in reversed([x for x in bad if x[0] < worst_ts]):
        if run[0][0] - b[0] > gap:
            break
        run.insert(0, b)
    for b in [x for x in bad if x[0] > worst_ts]:
        if b[0] - run[-1][0] > gap:
            break
        run.append(b)
    targets = sorted({t for b in run for t in b[2]})
    return {
        "worst": worst_q, "worst_ts": worst_ts, "from": run[0][0], "to": run[-1][0] + step,
        "dead_s": sum(1 for b in run if b[1] == 0) * step, "other_dips": len(bad) - len(run),
        "targets": targets, "n_targets": len(labels) - 1,
        "all_targets": len(targets) >= len(labels) - 1,
    }  # fmt: skip


def print_loss(loss: dict, server: str | None = None) -> None:
    scope = (
        "ALL targets"
        if loss["all_targets"]
        else f"{len(loss['targets'])}/{loss['n_targets']} targets"
    )
    head = f">>> {server}: PACKET LOSS" if server else ">>> PACKET LOSS"
    print(
        f"{head}: worst quality {loss['worst']:.0f} % @ {_hms(loss['worst_ts'])} UTC, "
        f"window {_hms(loss['from'])}-{_hms(loss['to'])} UTC, {scope}"
    )
    if loss["dead_s"]:
        where = (
            "to ALL its targets -- check where they are (often one location = one route, "
            "not the whole egress)"
            if loss["all_targets"]
            else "some targets only"
        )
        print(f"    100% loss for {loss['dead_s']:.0f} s -> FULL connectivity OUTAGE ({where})")
    if loss["other_dips"]:
        print(f"    (+ {loss['other_dips']} more dips outside this window)")
    for target in loss["targets"][:10]:
        print(f"      - {target}")


def fping_window(nd: Netdata, after: int, before: int | None, threshold: float) -> dict | str:
    """Latency over all targets plus packet loss; a str is the reason there is no summary.

    The key signal: when even the minimum rises, the shared path (the server's egress or
    peering) is slow, not one target.
    """
    latency = nd.data("fping.latency", after, before)
    loss = fping_loss(nd, after, before)
    _, labels, rows = _result(latency)
    empty = {"baseline": 0.0, "peak_max": 0.0, "peak_max_ts": None, "peak_min": 0.0,
             "peak_min_ts": None, "shared_path": False, "loss": loss, "spikes": []}  # fmt: skip
    if not rows:
        return empty if loss else "No fping data (is the fping plugin running on this server?)"
    if "minimum" not in labels or "maximum" not in labels:
        return f"Unexpected labels: {labels}"
    i_min, i_max = labels.index("minimum"), labels.index("maximum")
    mins = [(r[0], r[i_min]) for r in rows if i_min < len(r) and _number(r[i_min])]
    maxs = [(r[0], r[i_max]) for r in rows if i_max < len(r) and _number(r[i_max])]
    if not maxs:
        return "No latency values"
    normal = [v for _, v in mins if v < threshold]
    baseline = _median_low(normal) if normal else min((v for _, v in mins), default=0.0)
    peak_max_ts, peak_max = max(maxs, key=lambda x: x[1])
    peak_min_ts, peak_min = max(mins, key=lambda x: x[1]) if mins else (None, 0.0)
    min_at = dict(mins)
    return {
        "baseline": baseline, "peak_max": peak_max, "peak_max_ts": peak_max_ts,
        "peak_min": peak_min, "peak_min_ts": peak_min_ts,
        "shared_path": peak_min > max(threshold / 2, baseline * 3), "loss": loss,
        "spikes": [(ts, v, min_at.get(ts)) for ts, v in maxs if v > threshold],
    }  # fmt: skip


def print_window(nd: Netdata, res: dict, threshold: float) -> None:
    if res["loss"]:
        print_loss(res["loss"])
    if res["peak_max_ts"] is None:  # loss only, no latency samples
        return
    print(f"=== fping latency: {nd.host} | threshold {threshold:.0f}ms ===")
    print(f"baseline (median min): {res['baseline']:.1f} ms")
    print(f"PEAK max: {res['peak_max']:.1f} ms @ {_hms(res['peak_max_ts'])} UTC")
    print(f"PEAK min (across targets): {res['peak_min']:.1f} ms @ {_hms(res['peak_min_ts'])} UTC")
    if res["shared_path"]:
        print(
            ">>> NETWORK EVENT: the minimum rose too -> shared path "
            "(server egress/peering), not one target"
        )
    elif res["peak_max"] > threshold:
        print(">>> Spike in the maximum only -> one remote target slow, server egress OK")
    else:
        print(">>> OK: no significant latency spike")
    if res["spikes"]:
        print(f"\nbuckets over threshold ({len(res['spikes'])}):")
        for ts, v, mn in res["spikes"][:20]:
            shown = f"{mn:.1f}" if mn is not None else "-"
            print(f"  {_hms(ts)} UTC   max {v:8.1f} ms   min {shown:>8} ms")


def fping_per_target(nd: Netdata, after: int, before: int | None, threshold: float) -> int:
    _, labels, rows = _result(nd.data("fping.latency", after, before, group_by="instance"))
    if not rows or len(labels) < 2:
        print("No per-target fping data")
        return 0
    targets = []  # (name, baseline, peak)
    for i in range(1, len(labels)):
        values = [r[i] for r in rows if i < len(r) and _number(r[i])]
        if values:
            normal = [v for v in values if v < threshold]
            targets.append((labels[i], _median_low(normal) if normal else min(values), max(values)))
    if not targets:
        print("No latency values per target")
        return 0
    targets.sort(key=lambda t: t[2], reverse=True)
    bad = [t for t in targets if t[2] > threshold]
    ok = len(targets) - len(bad)
    print(f"=== fping per target: {nd.host} | threshold {threshold:.0f}ms ===")
    print(f"{'target':32s} {'baseline':>10s} {'peak':>10s}")
    for name, base, peak in targets:
        flag = "  <-- bad" if peak > threshold else ""
        print(f"{name[:32]:32s} {base:8.1f}ms {peak:8.1f}ms{flag}")
    if bad and ok:
        print(
            f"\n>>> LOCALIZATION: {len(bad)} targets bad, {ok} OK "
            "-> one segment is faulty (targets outside the OK group), not the whole uplink"
        )
    elif bad:
        print("\n>>> ALL targets bad -> server egress / its side of the network")
    return 0


def cache_name(server: str | None, host: str, target: str) -> str:
    """Cache basename (doc-2 "Generated file names"); host is normalized."""
    if server is not None:
        key = f"server-{server.lower()}"
    else:
        try:
            is_ipv6 = ipaddress.ip_address(host).version == 6
        except ValueError:
            is_ipv6 = False
        if not is_ipv6 and len(host) <= 100:
            key = f"host-{host}"
        else:
            key = "hostid-" + hashlib.sha256(host.encode()).hexdigest()[:32]
    name = f"{key}+{target.lower()}.json"
    if not _BASENAME_RE.fullmatch(name):  # parts are validated; this cannot happen
        raise CcaError(f"invalid cache file name '{validate.display(name)}'")
    return name


def _read_cache(path: Path) -> list[tuple[int, float]] | None:
    try:
        series = json.loads(path.read_text())["series"]
        return [(int(t), float(v)) for t, v in series]
    except (OSError, ValueError, KeyError, TypeError):
        return None  # unreadable or malformed: fetch again


def fping_history(nd: Netdata, args: argparse.Namespace, target: str, cache: Path,
                  after: int) -> dict | str:  # fmt: skip
    """Events = contiguous runs over the threshold lasting >= --min-seconds."""
    series = None if args.refresh else _read_cache(cache)
    source = f"cache {cache}"
    if series is None:
        data = nd.data("fping.latency", after, args.before, group_by="instance")
        _, labels, rows = _result(data)
        if not rows or len(labels) < 2:
            return "No fping history"
        columns = [i for i in range(1, len(labels)) if target.lower() in labels[i].lower()]
        if not columns:
            return f"No target matches --target '{target}'. Targets: {labels[1:]}"
        series = []
        for r in rows:
            values = [r[i] for i in columns if i < len(r) and _number(r[i])]
            if values and _number(r[0]):
                series.append((int(r[0]), max(values)))
        source = f"netdata {nd.host} (targets ~'{target}', {len(columns)})"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"host": nd.host, "target": target, "series": series}))
    if args.exclude_hours:
        series = [
            (t, v)
            for t, v in series
            if datetime.fromtimestamp(t, tz=UTC).hour not in args.exclude_hours
        ]
    if not series:
        return "Empty series"
    series.sort()
    gaps = [b[0] - a[0] for a, b in zip(series, series[1:])]
    step = _median_low(gaps) if gaps else 60  # sample resolution
    threshold = args.threshold
    # a coarse sample is the AVERAGE over its interval: short blips are smoothed out and
    # durations are quantized to the step
    events, run = [], None  # [start, end, peak, samples]
    for ts, v in series:
        if v > threshold:
            run = [ts, ts, v, 1] if run is None else [run[0], ts, max(run[2], v), run[3] + 1]
        elif run is not None:
            if run[1] - run[0] + step >= args.min_seconds:
                events.append(run)
            run = None
    if run is not None and run[1] - run[0] + step >= args.min_seconds:
        events.append(run)
    normal = [v for _, v in series if v <= threshold]
    by_month: dict[str, int] = {}
    for start, *_ in events:
        month = datetime.fromtimestamp(start, tz=UTC).strftime("%Y-%m")
        by_month[month] = by_month.get(month, 0) + 1
    return {
        "events": events, "baseline": _median_low(normal) if normal else 0,
        "by_month": by_month, "span_days": (series[-1][0] - series[0][0]) // 86400,
        "step": step, "source": source,
    }  # fmt: skip


def print_history(nd: Netdata, res: dict, args: argparse.Namespace, target: str) -> None:
    step, threshold, min_s = res["step"], args.threshold, args.min_seconds
    coarse = step > 90
    print(
        f"=== fping history: {nd.host} | pair ~'{target}' | {res['span_days']} days | "
        f"threshold {threshold:.0f}ms / >= {min_s}s ==="
    )
    print(
        f"source: {res['source']} | sample resolution ~{step}s | baseline {res['baseline']:.1f} ms"
    )
    print(f"EVENTS (sustained > threshold, >= {min_s}s): {len(res['events'])}")
    if coarse:
        print(
            f"!! COARSE RESOLUTION {step}s: 'peak' is a sample AVERAGE (the real peak is higher),"
        )
        print(
            f"   durations are quantized to {step}s. For detail: a recent pull "
            "(--after -604800) or live 'fping'."
        )
    print("\nper month (event count = relative trend):")
    for month in sorted(res["by_month"]):
        count = res["by_month"][month]
        print(f"  {month}   {count:3d}  {'#' * count}")
    if res["events"]:
        label = "avg/sample" if coarse else "peak"
        print("\nworst events:")
        for start, end, peak, n in sorted(res["events"], key=lambda e: e[2], reverse=True)[:12]:
            when = datetime.fromtimestamp(start, tz=UTC).strftime("%Y-%m-%d %H:%M")
            length = f"~{(end - start + step) // 60}m ({n}x{step}s)"
            print(f"  {when} UTC  {length}  {label} {peak:8.1f} ms")


def _history_target(args: argparse.Namespace, cfg: config.Config | None) -> str:
    target = args.target or (cfg.get("netdata.fping_target") if cfg else None)
    if target is None:
        raise CcaError("fping --history needs --target (or netdata.fping_target in .cca.toml)")
    return target


def _cache_path(
    args: argparse.Namespace, cfg: config.Config | None, nd: Netdata, target: str
) -> Path:
    if args.cache is not None and not args.all:
        return Path(args.cache)  # CLI path: from the CWD
    if cfg is not None:
        directory = cfg.resolve(cfg.get("netdata.fping_cache_dir"))
    else:
        directory = Path(DEFAULT_CACHE_DIR)
    path = directory / cache_name(nd.server, nd.host, target)
    if not path.resolve().is_relative_to(directory.resolve()):
        raise CcaError(f"fping cache {path} resolves outside {directory}")
    return path


def cmd_fping(nd: Netdata, args: argparse.Namespace, cfg: config.Config | None) -> int:
    after = args.after if args.after is not None else (HISTORY_AFTER if args.history else -900)
    if args.per_target:
        return fping_per_target(nd, after, args.before, args.threshold)
    if args.history:
        target = _history_target(args, cfg)
        res = fping_history(nd, args, target, _cache_path(args, cfg, nd, target), after)
        if isinstance(res, str):
            print(res)
        else:
            print_history(nd, res, args, target)
        return 0
    res = fping_window(nd, after, args.before, args.threshold)
    if isinstance(res, str):
        print(res)
    else:
        print_window(nd, res, args.threshold)
    return 0


def fping_all(args: argparse.Namespace, cfg: config.Config) -> int:
    """Scan every [servers] entry with netdata_host, each with its own transport."""
    servers = cfg.data["servers"]
    history = args.history
    after = args.after if args.after is not None else (HISTORY_AFTER if history else -900)
    target = _history_target(args, cfg) if history else None
    mode = "history" if history else "window"
    print(
        f"=== fping scan of {len(servers)} servers | {mode} | threshold {args.threshold:.0f}ms ==="
    )
    shared, losses = [], {}
    for name, server in servers.items():
        if "netdata_host" not in server:
            print(f"  {name:10s} -- not configured (no netdata_host)")
            continue
        nd = _client(cfg, name, server, None, ALL_TIMEOUT)
        try:
            if history:
                res = fping_history(nd, args, target, _cache_path(args, cfg, nd, target), after)
            else:
                res = fping_window(nd, after, args.before, args.threshold)
        except FetchError:
            res = None
        if not isinstance(res, dict):
            print(f"  {name:10s} -- unreachable / no fping")
            continue
        if history:
            months = sorted(res["by_month"])
            tail = "  ".join(f"{m[5:]}:{res['by_month'][m]}" for m in months) or "none"
            print(
                f"  {name:10s} events {len(res['events']):3d} in {res['span_days']:3d}d  "
                f"baseline {res['baseline']:6.1f}ms  | {tail}"
            )
            continue
        loss = res["loss"]
        if res["shared_path"]:
            shared.append(name)
        if loss:
            losses[name] = loss
        if loss and loss["dead_s"]:
            tag = "OUTAGE!"
        elif loss:
            tag = "LOSS!"
        elif res["shared_path"]:
            tag = "NET!"
        else:
            tag = "max" if res["peak_max"] > args.threshold else "ok"
        print(
            f"  {name:10s} baseline {res['baseline']:6.1f}ms  peak_max {res['peak_max']:8.1f}ms  "
            f"peak_min {res['peak_min']:8.1f}ms  [{tag}]"
        )
    if losses:
        print("\n=== PACKET LOSS (fping.quality) -- latency does not show this kind of outage ===")
        for name, loss in losses.items():
            print_loss(loss, name)
    if len(shared) >= 2:
        print(
            f"\n>>> CORRELATED NETWORK EVENT: {len(shared)} servers ({', '.join(shared)}) have a "
            "spike in the minimum -> peering/transit problem (not our server)"
        )
    elif shared:
        print(
            f"\n>>> NETWORK EVENT on {shared[0]} only: its own path, or an asymmetric "
            "(one-direction) fault -> check from the other side"
        )
    return 0


# --- entry


def _client(cfg: config.Config, name: str, server: dict[str, Any], transport: str | None,
            timeout: int | None = None) -> Netdata:  # fmt: skip
    if "netdata_host" not in server:
        raise CcaError(
            f"{cfg.path}: servers.{name}.netdata_host: required by this command but not set"
        )
    host = validate.host(server["netdata_host"])
    if "%" in host:  # a zone id does not fit the URL
        raise CcaError(f"{cfg.path}: servers.{name}.netdata_host: IPv6 zone id is not supported")
    port = server["netdata_port"]
    destination = None
    if (transport or server["netdata_transport"]) == "ssh":
        destination = ssh.target(cfg, name)
    return Netdata(host, port, destination, name, timeout)


def run(args: argparse.Namespace) -> int:
    command = args.netdata_command
    if command is None:
        print(args.netdata_help(), file=sys.stderr, end="")
        return 2
    server = getattr(args, "server", None)
    host = getattr(args, "host", None)
    port = getattr(args, "port", None)
    transport = getattr(args, "transport", None)
    fping_all_mode = command == "fping" and args.all
    if fping_all_mode and (
        any(x is not None for x in (server, host, port, transport, args.cache)) or args.per_target
    ):
        raise CcaError(
            "fping --all takes no --server, --host, --port, --transport, --cache or --per-target"
        )
    if server is not None and (host is not None or port is not None):
        raise CcaError("--server and --host/--port are mutually exclusive")
    if server is None and transport == "ssh" and not fping_all_mode:
        raise CcaError("--transport ssh needs --server (use --host for direct access)")

    cfg = config.load(args.config)  # optional: fping_target and the cache dir
    if fping_all_mode or server is not None:
        if cfg is None:
            cfg = config.require(args.config)  # raises with the discovery message
    if fping_all_mode:
        return fping_all(args, cfg)
    if server is not None:
        nd = _client(cfg, server, cfg.server(server), transport)
        via = f"ssh {nd.destination} -> " if nd.destination else ""
        print(f"Using server {server} -> {via}{nd.address()}", file=sys.stderr)
    else:
        nd = Netdata(host or "localhost", port or DEFAULT_PORT)

    if command == "fping":
        return cmd_fping(nd, args, cfg)
    handler = {
        "list": cmd_list, "query": cmd_query, "stats": cmd_stats, "top": cmd_top,
        "discover": cmd_discover, "meta": cmd_meta,
    }[command]  # fmt: skip
    return handler(nd, args)
