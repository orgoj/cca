"""cca cloudflare: DNS, WAF rules, zone audit and exports through the Cloudflare SDK (doc-5)."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import re
import sys
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from cca import config, secrets, validate
from cca.output import CcaError

MAX_BODY = 64 * 1024 * 1024  # API response cap, decoded
DEADLINE = 60  # seconds per request: headers and the whole body
TIMEOUT = httpx.Timeout(30, connect=10)
MAX_RETRIES = 2  # SDK default (legacy): connection errors, 408, 409, 429, 5xx
PER_PAGE = 50
MAX_PAGES = 1000
ZONE_MAX = 150  # doc-2 "Generated file names"
# inner transport of the SDK's httpx client; tests put an httpx.MockTransport here
TRANSPORT: httpx.BaseTransport | None = None

SHOW_RECORDS = ("@", "www", "_dmarc")
AUDIT_SETTINGS = (
    "security_level", "challenge_ttl", "browser_check", "pseudo_ipv4", "always_use_https",
    "ssl", "min_tls_version", "development_mode", "cache_level", "ipv6", "email_obfuscation",
    "hotlink_protection",
)  # fmt: skip
# group -> (rulesets phase, label, free-plan quota)
PHASES = {
    "waf": ("http_request_firewall_custom", "WAF Custom Rules", 5),
    "ratelimit": ("http_ratelimit", "Rate Limiting Rules", 1),
    "config": ("http_config_settings", "Configuration Rules", 10),
}
DUMP_FIELDS = ("name", "type", "content", "ttl", "proxied", "priority", "data", "comment", "tags")
BOT_FIELDS = (
    "ai_bots_protection", "ai_search", "ai_training", "ai_user", "crawler_protection",
    "is_robots_txt_managed", "fight_mode",
)  # fmt: skip
COUNTRY_EXPR = re.compile(r"ip\.(?:src|geoip)\.country\s+in\s+\{([^}]*)\}")
CRAWLERS = re.compile(r"googlebot|bingbot|seznambot|applebot|yandexbot|duckduckbot", re.I)
# actions the CLI can build a complete rule for; others need action_parameters
WRITABLE_ACTIONS = ("block", "managed_challenge", "js_challenge", "challenge", "log")
READONLY_RULE_FIELDS = ("id", "version", "last_updated")
# a missing zone entrypoint ruleset is recognized only by this 404 message; any other read
# error is fatal so an empty list never creates a new ruleset
MISSING_ENTRYPOINT = re.compile(
    r"could not find (entry ?point )?ruleset|ruleset[^.]*not found|entry ?point[^.]*not found",
    re.I,
)
API_ID_RE = re.compile(r"[0-9a-f]{32}")
WINDOWS_DEVICES = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])")
_BASENAME_RE = re.compile(r"[a-z0-9._+-]{1,200}")
PLAN_END = "PLAN - nothing changed in Cloudflare (add --apply to write)."

GRAPHQL_EVENTS = """
query($zoneTag: String!, $since: Time!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      firewallEventsAdaptive(
        filter: {datetime_geq: $since}
        limit: $limit
        orderBy: [datetime_DESC]
      ) {
        datetime
        action
        source
        ruleId
        clientCountryName
        clientAsn
        clientIP
        clientRequestPath
        userAgent
      }
    }
  }
}
"""

GRAPHQL_TRAFFIC = """
query($zoneTag: String!, $since: Time!, $until: Time!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequestsAdaptiveGroups(
        filter: {datetime_geq: $since, datetime_lt: $until}
        limit: $limit
        orderBy: [__DIMENSION___ASC]
      ) {
        dimensions { __DIMENSION__ }
        count
        sum { edgeResponseBytes visits }
      }
    }
  }
}
"""

GRAPHQL_TRAFFIC_DAILY = """
query($zoneTag: String!, $since: Date!, $until: Date!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequests1dGroups(
        filter: {date_geq: $since, date_leq: $until}
        limit: $limit
        orderBy: [date_ASC]
      ) {
        dimensions { date }
        sum { requests pageViews bytes threats cachedRequests }
        uniq { uniques }
      }
    }
  }
}
"""

GRAPHQL_TRAFFIC_BREAKDOWN = """
query($zoneTag: String!, $since: Time!, $until: Time!, $limit: Int!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequestsAdaptiveGroups(
        filter: {datetime_geq: $since, datetime_lt: $until}
        limit: $limit
        orderBy: [count_DESC]
      ) {
        dimensions { __DIMENSION__ }
        count
        sum { visits }
      }
    }
  }
}
"""

EPILOG = """\
examples:
  cca cloudflare zone list --name example
  cca cloudflare zone info example.com
  cca cloudflare dns show-domain example.com
  cca cloudflare dns ensure-cname example.com --name www --target target.example.net
  cca cloudflare waf list example.com
  cca cloudflare waf add example.com --description "block admin" --action block \\
      --expression '(http.request.uri.path contains "/admin")' --position 1
  cca cloudflare events example.com --since 2h
  cca cloudflare export example.com && cca cloudflare diff example.com

Write commands (dns ensure-*, dns restore-zone, waf add/edit/move) only plan; --apply
changes Cloudflare. The token comes from the sops file secrets.cloudflare (.cca.toml).
"""


class RunError(CcaError):
    """A runtime failure (legacy `fail()`): exit 1."""

    def __init__(self, message: str):
        super().__init__(message, 1)


class LimitExceeded(BaseException):  # noqa: N818
    """Response cap or deadline hit; a BaseException so the SDK never retries it."""


def _d(value: Any) -> str:
    """An API or file string safe to print."""
    return validate.display(str(value))


def _escape(c: str) -> str:
    o = ord(c)
    if o <= 0xFFFF:
        return f"\\u{o:04x}"
    o -= 0x10000
    return f"\\u{0xD800 + (o >> 10):04x}\\u{0xDC00 + (o & 0x3FF):04x}"


def json_text(value: Any, sort_keys: bool = True) -> str:
    """Indented JSON whose non-printable characters are \\u escapes (still valid JSON)."""
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=sort_keys)
    return "".join(c if c.isprintable() or c == "\n" else _escape(c) for c in text)


def _write(path: Path, text: str, mode: str = "w") -> None:
    try:
        with open(path, mode, encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        raise RunError(f"cannot write {_d(path)}: {e.strerror}") from None


# ---------------------------------------------------------------- client


class _Limited(httpx.BaseTransport):
    """Reads each response (decoded) within MAX_BODY and DEADLINE, headers included."""

    def __init__(self, inner: httpx.BaseTransport):
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        outcome: list = []

        def work() -> None:
            try:
                raw = self.inner.handle_request(request)
                response = httpx.Response(
                    raw.status_code, headers=raw.headers, stream=raw.stream, request=request
                )
                body = bytearray()
                try:
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BODY:
                            raise LimitExceeded(f"response larger than {MAX_BODY} bytes")
                finally:
                    response.close()
                headers = [
                    (k, v)
                    for k, v in raw.headers.multi_items()
                    if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                ]
                outcome.append(
                    httpx.Response(
                        raw.status_code, headers=headers, content=bytes(body), request=request
                    )
                )
            except BaseException as e:  # noqa: BLE001 - re-raised in the caller
                outcome.append(e)

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        worker.join(DEADLINE)
        if not outcome:
            raise LimitExceeded(f"no complete response within {DEADLINE} s")
        if isinstance(outcome[0], BaseException):
            raise outcome[0]
        return outcome[0]

    def close(self) -> None:
        self.inner.close()


def make_client(token: str, base_url: str):
    """SDK client with explicit token and endpoint; every ambient SDK fallback disabled."""
    from cloudflare import Cloudflare

    for name in ("cloudflare", "httpx", "httpcore"):  # CLOUDFLARE_LOG
        logging.getLogger(name).setLevel(logging.WARNING)
    inner = TRANSPORT if TRANSPORT is not None else httpx.HTTPTransport(trust_env=False)
    http_client = httpx.Client(
        transport=_Limited(inner),
        trust_env=False,
        follow_redirects=False,
        timeout=TIMEOUT,
        headers={"Accept-Encoding": "identity"},
    )
    client = Cloudflare(
        api_token=token, base_url=base_url, http_client=http_client, max_retries=MAX_RETRIES
    )
    # the constructor reads these from the environment when not given
    client.api_key = None  # CLOUDFLARE_API_KEY
    client.api_email = None  # CLOUDFLARE_EMAIL
    client.user_service_key = None  # CLOUDFLARE_API_USER_SERVICE_KEY
    client._custom_headers = {}  # CLOUDFLARE_CUSTOM_HEADERS
    return client


def plain(value: Any) -> Any:
    """SDK models to JSON-serializable data: only the fields the API returned."""
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json", exclude_unset=True))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():  # SDK float fields (ttl) of JSON ints
        return int(value)
    return value


def pages(list_fn, **params) -> list[dict]:
    """Every item of a paginated list; stops on an empty or short page or total_pages."""
    items: list[dict] = []
    per_page = params.setdefault("per_page", PER_PAGE)
    for page in range(1, MAX_PAGES + 1):
        response = list_fn(page=page, **params)
        batch = [plain(item) for item in (getattr(response, "result", None) or [])]
        items.extend(batch)
        info = getattr(response, "result_info", None)
        total = getattr(info, "total_pages", None)
        if len(batch) < per_page or (total is not None and page >= total):
            return items
    raise RunError(f"more than {MAX_PAGES} pages of {per_page} items")


def api_id(value: Any, what: str) -> str:
    """An id from the API that goes into a request path."""
    if not isinstance(value, str) or not API_ID_RE.fullmatch(value):
        raise RunError(f"unexpected {what} id from the API: {_d(value)}")
    return value


def api_error(exc: BaseException) -> str:
    """Readable, escaped text of an SDK error (never a traceback)."""
    import cloudflare

    if isinstance(exc, cloudflare.APIStatusError):
        body = exc.body
        errors = body.get("errors") if isinstance(body, dict) else None
        if isinstance(errors, list) and errors:
            detail = "; ".join(
                f"{e.get('code', '?')}: {e.get('message', '?')}" if isinstance(e, dict) else str(e)
                for e in errors
            )
        else:
            detail = str(body) if body is not None else exc.message
        return _d(f"HTTP {exc.status_code}: {detail}")
    if isinstance(exc, cloudflare.APIConnectionError) and exc.__cause__ is not None:
        return _d(f"{exc.message} ({type(exc.__cause__).__name__}: {exc.__cause__})")
    return _d(getattr(exc, "message", None) or str(exc))


def status_code(exc: BaseException) -> int | None:
    return getattr(exc, "status_code", None)


# ---------------------------------------------------------------- arguments


def _zone(value: str) -> str:
    name = validate.dns_name(value)
    if name is None:
        raise argparse.ArgumentTypeError(f"invalid zone name '{validate.display(value)}'")
    return name


def _label(value: str) -> str:
    if value in ("", "@"):
        return "@"
    name = validate.dns_name(value)
    if name is None or value.endswith("."):
        raise argparse.ArgumentTypeError(f"invalid record name '{validate.display(value)}'")
    return name


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer: '{validate.display(value)}'")
    return number


def _rule(value: str) -> str:
    if not value or validate.has_control(value):
        raise argparse.ArgumentTypeError("must be a rule id, description or position")
    return value


def _text(value: str) -> str:
    if validate.has_control(value):
        raise argparse.ArgumentTypeError("must not contain control characters")
    return value


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """'30m', '2h', '1d' or an ISO time (naive = UTC) -> aware UTC datetime."""
    now = now or datetime.now(UTC)
    match = re.fullmatch(r"(\d+)([mhd])", value.strip())
    if match:
        unit = {"m": "minutes", "h": "hours", "d": "days"}[match.group(2)]
        try:
            return now - timedelta(**{unit: int(match.group(1))})
        except OverflowError:
            pass
    else:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    raise RunError(f"invalid --since '{_d(value)}' (use 30m, 2h, 1d or an ISO time)")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.description = "Cloudflare zones: DNS records, WAF rules, audit, exports."
    parser.epilog = EPILOG
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.set_defaults(cf_help=parser.format_help, cf_command=None)
    groups = parser.add_subparsers(dest="cf_group", metavar="GROUP")

    def group(name: str, help_text: str) -> argparse._SubParsersAction:
        p = groups.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(cf_help=p.format_help)
        return p.add_subparsers(dest="cf_command", metavar="COMMAND")

    def command(sub, name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_text, description=help_text)

    def apply(p: argparse.ArgumentParser) -> None:
        p.add_argument("--apply", action="store_true", help="change Cloudflare (default: plan)")

    sub = group("token", "the API token")
    command(sub, "verify", "check the token and print its policies")

    sub = group("zone", "zones and their settings")
    p = command(sub, "list", "all zones the token can see")
    p.add_argument("--name", type=_text, help="only zones whose name contains this substring")
    p = command(sub, "info", "plan, audit settings, rule counts with quotas")
    p.add_argument("domain", type=_zone)
    p = command(sub, "settings", "zone settings")
    p.add_argument("domain", type=_zone)
    p.add_argument("--setting", action="append", type=_text, help="only this key (repeatable)")

    sub = group("dns", "DNS records")
    p = command(sub, "show-domain", "records for @, www and _dmarc")
    p.add_argument("domains", nargs="+", type=_zone, metavar="DOMAIN")
    p = command(sub, "show-dkim", "all *._domainkey.* records")
    p.add_argument("domains", nargs="+", type=_zone, metavar="DOMAIN")
    p = command(sub, "ensure-dkim", "ensure DKIM CNAMEs S._domainkey.ZONE -> S._domainkey.T")
    p.add_argument("--selector", action="append", required=True, type=_zone, metavar="S",
                   help="DKIM selector (repeatable)")  # fmt: skip
    p.add_argument("--target-domain", required=True, type=_zone, metavar="T")
    p.add_argument("domains", nargs="+", type=_zone, metavar="DOMAIN")
    apply(p)
    p = command(sub, "ensure-cname", "ensure one CNAME record")
    p.add_argument("domain", type=_zone)
    p.add_argument("--name", required=True, type=_label, help="label without the zone, @ = apex")
    p.add_argument("--target", required=True, type=_zone, help="CNAME target (FQDN)")
    apply(p)
    p = command(sub, "dump-zone", "all DNS records as JSON (cloudflare-dns-dump/1)")
    p.add_argument("domain", type=_zone)
    p.add_argument("-o", "--output", help="write to this file (default: stdout)")
    p = command(sub, "restore-zone", "restore DNS records from a dump-zone file")
    p.add_argument("input", help="dump-zone JSON file")
    p.add_argument("--domain", type=_zone, help="zone (default: from the file)")
    p.add_argument("--delete-extras", action="store_true", help="delete records not in the file")
    apply(p)

    rule_help = "rule id from `waf list`, exact description, or position (plan only)"
    for kind, (_, label, _quota) in PHASES.items():
        sub = group(kind, label)
        p = command(sub, "list", f"list {label}")
        p.add_argument("domain", type=_zone)
        if kind != "waf":
            continue
        p = command(sub, "countries", "country lists of WAF rules across all zones")
        p.add_argument("--name", type=_text, help="only zones whose name contains this substring")
        p.add_argument("-o", "--output", help="also write the result as JSON")

        p = command(sub, "add", "add a WAF custom rule (default: plan)")
        p.add_argument("domain", type=_zone)
        p.add_argument("--description", required=True, type=_text)
        p.add_argument("--action", required=True, choices=WRITABLE_ACTIONS)
        p.add_argument("--expression", required=True, type=_text,
                       help="Cloudflare expression (validated by Cloudflare)")  # fmt: skip
        place = p.add_mutually_exclusive_group()
        place.add_argument("--before", type=_rule, help=f"place right before: {rule_help}")
        place.add_argument("--after", type=_rule, help=f"place right after: {rule_help}")
        place.add_argument("--position", type=_positive, help="target position, 1 = first")
        p.add_argument("--disabled", action="store_true", help="create the rule disabled")
        apply(p)

        p = command(sub, "edit", "change a WAF custom rule (default: plan)")
        p.add_argument("domain", type=_zone)
        p.add_argument("--rule", required=True, type=_rule, help=rule_help)
        p.add_argument("--description", type=_text)
        p.add_argument("--expression", type=_text)
        p.add_argument("--action", choices=WRITABLE_ACTIONS)
        state = p.add_mutually_exclusive_group()
        state.add_argument("--enable", action="store_true")
        state.add_argument("--disable", action="store_true")
        apply(p)

        p = command(sub, "move", "reorder a WAF custom rule (default: plan)")
        p.add_argument("domain", type=_zone)
        p.add_argument("--rule", required=True, type=_rule, help=rule_help)
        place = p.add_mutually_exclusive_group(required=True)
        place.add_argument("--before", type=_rule, help=f"move right before: {rule_help}")
        place.add_argument("--after", type=_rule, help=f"move right after: {rule_help}")
        place.add_argument("--position", type=_positive, help="target position, 1 = first")
        apply(p)

    sub = group("access", "IP access rules")
    p = command(sub, "list", "list IP access rules")
    p.add_argument("domain", type=_zone)
    sub = group("ua", "user agent blocking rules")
    p = command(sub, "list", "list user agent rules")
    p.add_argument("domain", type=_zone)
    sub = group("uam", "Under Attack Mode")
    p = command(sub, "status", "global and per-URL Under Attack Mode")
    p.add_argument("domain", type=_zone)
    sub = group("bots", "AI crawlers and Bot Fight Mode")
    p = command(sub, "status", "bot settings; all zones without DOMAIN")
    p.add_argument("domain", nargs="?", type=_zone)
    p.add_argument("--raw", action="store_true", help="print the full JSON per zone")

    p = groups.add_parser("events", help="security events (free plan: 24 h retention)")
    p.add_argument("domain", type=_zone)
    p.add_argument("--since", default="2h", help="30m, 2h, 1d or an ISO time (default: 2h)")
    p.add_argument("--limit", type=_positive, default=1000, help="maximum events (default: 1000)")
    p.add_argument("--raw", action="store_true", help="one line per event instead of a summary")

    p = groups.add_parser("analytics", help="zone traffic: requests, visits, bytes")
    p.add_argument("domain", type=_zone)
    p.add_argument("--since", default="24h", help="24h, 7d or an ISO time (default: 24h)")
    p.add_argument("--by", choices=("hour", "day"), default="hour", help="default: hour")
    p.add_argument("--limit", type=_positive, default=200, help="maximum groups (default: 200)")
    p.add_argument("--no-breakdown", action="store_true",
                   help="skip the country, status and cache breakdowns")  # fmt: skip

    p = groups.add_parser("export", help="write the zone state to cloudflare.export_dir/ZONE.json")
    p.add_argument("domain", type=_zone)
    p.add_argument("-o", "--output", help="this file instead (from the current directory)")

    p = groups.add_parser("diff", help="compare the live zone with its stored export")
    p.add_argument("domain", type=_zone)
    p.add_argument("-i", "--input", help="this file instead (from the current directory)")


# ---------------------------------------------------------------- files


def zone_key(zone: str) -> str:
    """The zone part of generated names (doc-2): Windows device names hashed."""
    if len(zone) > ZONE_MAX:
        raise CcaError(f"zone name longer than {ZONE_MAX} characters: {zone}")
    if WINDOWS_DEVICES.fullmatch(zone.split(".", 1)[0]):
        return "zone+" + hashlib.sha256(zone.encode()).hexdigest()[:32]
    return zone


def export_name(zone: str) -> str:
    return _basename(f"{zone_key(zone)}.json")


def snapshot_name(zone: str, stamp: datetime, serial: int = 1) -> str:
    suffix = "" if serial == 1 else f"-{serial}"
    return _basename(f"{zone_key(zone)}+{stamp.strftime('%Y%m%dt%H%M%Sz')}{suffix}.json")


def _basename(name: str) -> str:
    if not _BASENAME_RE.fullmatch(name):  # parts are validated; this cannot happen
        raise CcaError(f"invalid file name '{validate.display(name)}'")
    return name


def _in_dir(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.resolve().is_relative_to(directory.resolve()):
        raise CcaError(f"{path} resolves outside {directory}")
    if path.is_symlink():  # could alias another zone's file inside the directory
        raise CcaError(f"{path} is a symbolic link")
    return path


# ---------------------------------------------------------------- reads


class Session:
    def __init__(self, cfg: config.Config, client):
        self.cfg = cfg
        self.client = client

    @property
    def export_dir(self) -> Path:
        return self.cfg.resolve(self.cfg.get("cloudflare.export_dir"))

    def zones(self, name: str | None = None) -> list[dict]:
        params = {"name": name} if name else {}
        zones = pages(self.client.zones.list, **params)
        for zone in zones:
            api_id(zone.get("id"), "zone")
        return zones

    def zone(self, domain: str) -> dict:
        exact = [z for z in self.zones(domain) if str(z.get("name", "")).lower() == domain]
        if not exact:
            raise RunError(f"Cloudflare zone '{domain}' not found")
        if len(exact) > 1:
            raise RunError(f"more than one Cloudflare zone named '{domain}'")
        return exact[0]

    def records(self, zone_id: str, name: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"zone_id": zone_id, "per_page": 100}
        if name is not None:
            params["name"] = {"exact": name}
        return pages(self.client.dns.records.list, **params)

    def settings(self, zone_id: str) -> dict:
        """All zone settings as {id: value}, one request."""
        try:
            raw = self.client.get(f"/zones/{zone_id}/settings", cast_to=object)
        except Exception as exc:  # noqa: BLE001 - reported, never a traceback
            raise RunError(f"cannot read zone settings: {api_error(exc)}") from None
        items = plain(raw)
        if isinstance(items, dict):
            items = items.get("result") or []
        out = {}
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and "id" in item:
                out[str(item["id"])] = item.get("value")
        return out

    def bot_management(self, zone_id: str) -> dict:
        import cloudflare

        try:
            raw = self.client.get(f"/zones/{zone_id}/bot_management", cast_to=object)
        except cloudflare.APIStatusError as exc:
            return {"_error": api_error(exc)}
        data = plain(raw)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        return data if isinstance(data, dict) else {}

    def phase(self, zone_id: str, phase: str, any_404: bool = False) -> tuple[str | None, list]:
        """(ruleset id, rules); (None, []) for a missing entrypoint.

        Write paths (any_404 False) accept only the recognized missing-entrypoint 404.
        """
        try:
            response = self.client.rulesets.phases.get(phase, zone_id=zone_id)
        except Exception as exc:  # noqa: BLE001
            if status_code(exc) == 404 and (any_404 or MISSING_ENTRYPOINT.search(str(exc))):
                return None, []
            raise RunError(f"cannot read rules of phase {phase}: {api_error(exc)}") from None
        data = plain(response)
        rules = [r for r in (data.get("rules") or []) if isinstance(r, dict)]
        return api_id(data.get("id"), "ruleset"), rules

    def phase_rules(self, zone_id: str, phase: str) -> list[dict]:
        """Rules for reading: any 404 means no rules."""
        return self.phase(zone_id, phase, any_404=True)[1]

    def access_rules(self, zone_id: str) -> list[dict]:
        return pages(self.client.firewall.access_rules.list, zone_id=zone_id, per_page=100)

    def ua_rules(self, zone_id: str) -> list[dict]:
        import cloudflare

        try:
            return pages(self.client.firewall.ua_rules.list, zone_id=zone_id, per_page=100)
        except cloudflare.APIStatusError:  # legacy endpoint, missing on some zones
            return []

    def graphql(self, query: str, variables: dict, field: str) -> list[dict]:
        try:
            raw = self.client.post(
                "/graphql", body={"query": query, "variables": variables}, cast_to=object
            )
        except Exception as exc:  # noqa: BLE001
            raise RunError(f"GraphQL request failed: {api_error(exc)}") from None
        data = plain(raw)
        if not isinstance(data, dict):
            raise RunError("GraphQL: unexpected response")
        if data.get("errors"):
            errors = data["errors"] if isinstance(data["errors"], list) else [data["errors"]]
            messages = "; ".join(
                str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors
            )
            raise RunError(f"GraphQL error: {_d(messages)}")
        zones = ((data.get("data") or {}).get("viewer") or {}).get("zones") or []
        if not zones or not isinstance(zones[0], dict):
            return []
        return [row for row in (zones[0].get(field) or []) if isinstance(row, dict)]

    def state(self, domain: str) -> dict:
        """Zone export, schema cloudflare-zone-export/1."""
        zone = self.zone(domain)
        zone_id = zone["id"]
        settings = self.settings(zone_id)
        records = sorted((record_to_dict(r) for r in self.records(zone_id)), key=record_sort_key)
        return {
            "schema": "cloudflare-zone-export/1",
            "exported_at": datetime.now(UTC).isoformat(),
            "zone": {"id": zone_id, "name": zone.get("name"), "status": zone.get("status")},
            "settings": {key: settings[key] for key in AUDIT_SETTINGS if key in settings},
            "waf_custom_rules": self.phase_rules(zone_id, PHASES["waf"][0]),
            "ratelimit_rules": self.phase_rules(zone_id, PHASES["ratelimit"][0]),
            "config_rules": self.phase_rules(zone_id, PHASES["config"][0]),
            "ip_access_rules": self.access_rules(zone_id),
            "user_agent_rules": self.ua_rules(zone_id),
            "dns_records": records,
        }


def record_to_dict(record: dict) -> dict:
    return {f: record[f] for f in DUMP_FIELDS if record.get(f) is not None}


def record_sort_key(record: dict) -> tuple:
    return (
        str(record.get("name", "")),
        str(record.get("type", "")),
        str(record.get("content", "")),
    )


def normalize_content(value: Any) -> str:
    return str(value).rstrip(".")


def fqdn(host: str, zone_name: str) -> str:
    return zone_name if host in ("", "@") else f"{host}.{zone_name}"


def format_record(record: dict) -> str:
    text = (
        f"{record.get('name', '?')} {record.get('type', '?')} "
        f"{normalize_content(record.get('content', ''))} ttl={record.get('ttl', '?')}"
    )
    if record.get("proxied") is not None:
        text += f" proxied={str(bool(record['proxied'])).lower()}"
    return _d(text)


def format_rule(rule: dict) -> list[str]:
    state = "" if rule.get("enabled", True) else " [DISABLED]"
    description = rule.get("description") or "(no description)"
    lines = [f"[{_d(rule.get('action', '?'))}]{state} {_d(description)}"]
    if rule.get("id"):
        lines.append(f"  id: {_d(rule['id'])}")
    if rule.get("expression"):
        lines.append(f"  expr: {_d(rule['expression'])}")
    if rule.get("action_parameters"):
        lines.append(f"  params: {_d(json.dumps(rule['action_parameters'], ensure_ascii=False))}")
    if rule.get("ratelimit"):
        lines.append(f"  ratelimit: {_d(json.dumps(rule['ratelimit'], ensure_ascii=False))}")
    return lines


def rule_countries(rule: dict) -> list[str]:
    found = []
    for group in COUNTRY_EXPR.findall(str(rule.get("expression") or "")):
        found.extend(re.findall(r'"([A-Z]{2})"', group))
    return found


def _num(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def human_bytes(value: float) -> str:
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}".replace(",", " ")
        value /= 1024
    return f"{value} B"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- read commands


def cmd_token_verify(s: Session, args: argparse.Namespace) -> int:
    import cloudflare

    verified = plain(s.client.user.tokens.verify()) or {}
    token_id = verified.get("id", "?")
    print("=== token ===")
    print(f"id:      {_d(token_id)}")
    print(f"status:  {_d(verified.get('status', '?'))}")
    if verified.get("expires_on"):
        print(f"expires: {_d(verified['expires_on'])}")
    print("--- policies ---")
    try:
        tokens = pages(s.client.user.tokens.list)
    except cloudflare.APIStatusError as exc:
        print("unavailable: the token lacks the 'User API Tokens Read' permission")
        print(f"  ({type(exc).__name__})")
        return 0
    mine = [t for t in tokens if t.get("id") == token_id]
    if not mine:
        print("token not found in the account token list")
        return 0
    for policy in mine[0].get("policies") or []:
        groups = ", ".join(str(g.get("name", "?")) for g in policy.get("permission_groups") or [])
        print(f"{_d(policy.get('effect', '?'))}: {_d(groups)}")
        for key, value in (policy.get("resources") or {}).items():
            print(f"  {_d(key)} = {_d(value)}")
    return 0


def _sorted_zones(s: Session, needle: str | None) -> list[dict]:
    zones = s.zones()
    if needle:
        zones = [z for z in zones if needle.lower() in str(z.get("name") or "").lower()]
    return sorted(zones, key=lambda z: str(z.get("name") or ""))


def cmd_zone_list(s: Session, args: argparse.Namespace) -> int:
    zones = _sorted_zones(s, args.name)
    for zone in zones:
        print(f"{_d(zone.get('name', '?'))}\t{_d(zone.get('status', '?'))}\t{_d(zone['id'])}")
    print(f"--- {len(zones)} zones ---")
    return 0


def cmd_zone_info(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    zone_id = zone["id"]
    plan = zone.get("plan") or {}
    print(f"=== {_d(zone.get('name'))} ===")
    print(f"zone_id:     {zone_id}")
    print(f"status:      {_d(zone.get('status'))}")
    print(f"plan:        {_d(plan.get('name', '?'))}")
    print(f"paused:      {_d(zone.get('paused'))}")
    print(f"nameservers: {_d(', '.join(str(n) for n in zone.get('name_servers') or []))}")
    settings = s.settings(zone_id)
    print("--- settings ---")
    for key in AUDIT_SETTINGS:
        if key in settings:
            print(f"{key}: {_d(settings[key])}")
    print("--- rules ---")
    for phase, label, quota in PHASES.values():
        print(f"{label}: {len(s.phase_rules(zone_id, phase))}/{quota}")
    print(f"IP Access Rules: {len(s.access_rules(zone_id))}")
    print(f"User Agent Rules: {len(s.ua_rules(zone_id))}")
    return 0


def cmd_zone_settings(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    settings = s.settings(zone["id"])
    print(f"=== {_d(zone.get('name'))} settings ===")
    for key in args.setting or sorted(settings):
        if key not in settings:
            print(f"{_d(key)}: (not available on this plan)")
            continue
        value = settings[key]
        if isinstance(value, dict | list):
            value = json.dumps(value, ensure_ascii=False)
        print(f"{_d(key)}: {_d(value)}")
    return 0


def cmd_show_domain(s: Session, args: argparse.Namespace) -> int:
    for index, domain in enumerate(args.domains):
        if index:
            print()
        zone = s.zone(domain)
        zone_name = str(zone.get("name"))
        print(f"=== {_d(zone_name)} ===")
        print(f"zone_id: {zone['id']}")
        for host in SHOW_RECORDS:
            records = s.records(zone["id"], fqdn(host, zone_name))
            label = _d(zone_name if host == "@" else host)
            if not records:
                print(f"{label}: MISSING")
            for record in records:
                print(f"{label}: {format_record(record)}")
    return 0


def cmd_show_dkim(s: Session, args: argparse.Namespace) -> int:
    for index, domain in enumerate(args.domains):
        if index:
            print()
        zone = s.zone(domain)
        print(f"=== {_d(zone.get('name'))} dkim ===")
        dkim = [r for r in s.records(zone["id"]) if "._domainkey." in str(r.get("name") or "")]
        if not dkim:
            print("no _domainkey records")
            continue
        for record in sorted(dkim, key=lambda r: str(r.get("name", ""))):
            print(format_record(record))
    return 0


def cmd_dump_zone(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    records = sorted((record_to_dict(r) for r in s.records(zone["id"])), key=record_sort_key)
    text = json_text(
        {
            "schema": "cloudflare-dns-dump/1",
            "exported_at": datetime.now(UTC).isoformat(),
            "zone": {"id": zone["id"], "name": zone.get("name")},
            "records": records,
        },
        sort_keys=False,
    )
    if args.output:
        _write(Path(args.output), text + "\n")
        print(f"DUMP {len(records)} records -> {_d(args.output)}")
    else:
        print(text)
    return 0


def cmd_rules_list(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    phase, label, quota = PHASES[args.cf_group]
    rules = s.phase_rules(zone["id"], phase)
    print(f"=== {_d(zone.get('name'))} - {label} ({len(rules)}/{quota}) ===")
    if not rules:
        print("no rules")
    for index, rule in enumerate(rules, start=1):
        lines = format_rule(rule)
        print(f"{index}. {lines[0]}")
        for line in lines[1:]:
            print(line)
    return 0


def cmd_waf_countries(s: Session, args: argparse.Namespace) -> int:
    per_zone: dict[str, list[str]] = {}
    actions: dict[str, set[str]] = {}
    for zone in _sorted_zones(s, args.name):
        name = str(zone.get("name"))
        countries: list[str] = []
        for rule in s.phase_rules(zone["id"], PHASES["waf"][0]):
            found = rule_countries(rule)
            if found:
                countries.extend(found)
                actions.setdefault(name, set()).add(str(rule.get("action")))
        per_zone[name] = sorted(set(countries))
    union = sorted({c for countries in per_zone.values() for c in countries})

    print(f"=== Country lists in WAF Custom Rules ({len(per_zone)} zones) ===")
    for name, countries in per_zone.items():
        if not countries:
            print(f"{_d(name):22} -   (no rule with countries)")
            continue
        action = "/".join(sorted(actions.get(name, {"?"})))
        print(f"{_d(name):22} {len(countries):2}  [{_d(action)}]  {' '.join(countries)}")
    print(f"\n--- union ({len(union)} countries) ---")
    print(" ".join(union))
    print("\n--- zones per country ---")
    counter = Counter(c for countries in per_zone.values() for c in countries)
    with_rule = [name for name, countries in per_zone.items() if countries]
    for country in union:
        missing = [name for name in with_rule if country not in per_zone[name]]
        note = "  missing: " + _d(", ".join(missing)) if missing else ""
        print(f"{country}  {counter[country]}/{len(with_rule)}{note}")
    if args.output:
        payload = {"generated_at": datetime.now(UTC).isoformat(), "union": union,
                   "per_zone": per_zone}  # fmt: skip
        _write(Path(args.output), json_text(payload) + "\n")
        print(f"\nJSON -> {_d(args.output)}")
    return 0


def cmd_access_list(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    rules = s.access_rules(zone["id"])
    print(f"=== {_d(zone.get('name'))} - IP Access Rules ({len(rules)}) ===")
    if not rules:
        print("no rules")
    for rule in sorted(rules, key=lambda r: str((r.get("configuration") or {}).get("value", ""))):
        conf = rule.get("configuration") or {}
        print(
            f"{_d(rule.get('mode', '?')):18} {_d(conf.get('target', '?')):12} "
            f"{_d(conf.get('value', '?')):24} {_d(rule.get('notes') or '')}"
        )
    return 0


def cmd_ua_list(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    rules = s.ua_rules(zone["id"])
    print(f"=== {_d(zone.get('name'))} - User Agent Rules ({len(rules)}) ===")
    for rule in rules:
        conf = rule.get("configuration") or {}
        print(
            f"{_d(rule.get('mode', '?')):18} {_d(conf.get('value', '?'))}  "
            f"{_d(rule.get('description') or '')}"
        )
    return 0


def cmd_uam_status(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    settings = s.settings(zone["id"])
    level = settings.get("security_level", "?")
    print(f"=== {_d(zone.get('name'))} - Under Attack Mode ===")
    print(f"security_level (global): {_d(level)}")
    print(f"UAM active globally:     {'YES' if level == 'under_attack' else 'no'}")
    print(f"challenge_ttl:           {_d(settings.get('challenge_ttl', '?'))}")
    print(f"browser_check:           {_d(settings.get('browser_check', '?'))}")
    per_url = [
        rule
        for rule in s.phase_rules(zone["id"], PHASES["config"][0])
        if (rule.get("action_parameters") or {}).get("security_level") == "under_attack"
    ]
    print(f"--- per-URL UAM (Configuration Rules): {len(per_url)} ---")
    for rule in per_url:
        for line in format_rule(rule):
            print(line)
    return 0


def bot_summary(conf: dict) -> str:
    if "_error" in conf:
        return f"ERROR: {conf['_error']}"
    parts = []
    for key in BOT_FIELDS:
        if key in conf:
            value = conf[key]
            if isinstance(value, bool):
                value = "on" if value else "off"
            parts.append(f"{key}={_d(value)}")
    return "  ".join(parts) if parts else "(no bot fields returned)"


def cmd_bots_status(s: Session, args: argparse.Namespace) -> int:
    zones = [s.zone(args.domain)] if args.domain else _sorted_zones(s, None)
    print("=== AI crawlers and bots (read-only) ===")
    print("The token sees zones of every account it can access; check the account column.")
    for zone in zones:
        account = (zone.get("account") or {}).get("name") or "?"
        conf = s.bot_management(zone["id"])
        print(f"{_d(zone.get('name', '?')):26} {_d(account):34} {bot_summary(conf)}")
        if args.raw and "_error" not in conf:
            print(json_text(conf))
    print(f"--- {len(zones)} zones ---")
    return 0


def cmd_events(s: Session, args: argparse.Namespace) -> int:
    zone = s.zone(args.domain)
    since = parse_since(args.since)
    # the free plan keeps 24 h and GraphQL rejects a wider window; one minute of margin
    oldest = datetime.now(UTC) - timedelta(hours=24) + timedelta(minutes=1)
    if since < oldest:
        print(
            f"NOTE: --since clamped to {oldest.strftime('%Y-%m-%d %H:%M')} UTC "
            "(free plan retention is 24 h)."
        )
        since = oldest
    variables = {"zoneTag": zone["id"], "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "limit": args.limit}  # fmt: skip
    events = s.graphql(GRAPHQL_EVENTS, variables, "firewallEventsAdaptive")
    print(
        f"=== {_d(zone.get('name'))} - Security Events since "
        f"{since.strftime('%Y-%m-%d %H:%M')} UTC ==="
    )
    print(f"events: {len(events)} (limit {args.limit}, free plan retention is 24 h)")
    if not events:
        return 0
    if args.raw:
        for e in events:
            print(
                f"{_d(e.get('datetime'))} {_d(e.get('action')):18} "
                f"{_d(e.get('clientCountryName', '?')):4} {_d(e.get('clientIP', '?')):39} "
                f"{_d(e.get('clientRequestPath', ''))}  UA={_d(e.get('userAgent', ''))}"
            )
        return 0
    # search engines must never be challenged; a hit means the rule is wrong
    crawlers = [e for e in events if CRAWLERS.search(str(e.get("userAgent") or ""))]
    if crawlers:
        print(f"WARNING: {len(crawlers)} hits on declared search engine crawlers - check the rule!")
        for e in crawlers[:10]:
            print(
                f"   {_d(e.get('action'))} {_d(e.get('clientCountryName'))} "
                f"{_d(e.get('userAgent'))}"
            )
    else:
        print("search engine check: no declared crawler among the hits - OK")
    summaries = (("action", "action"), ("source", "source"), ("country", "clientCountryName"),
                 ("top paths", "clientRequestPath"))  # fmt: skip
    for label, key in summaries:
        print(f"--- {label} ---")
        for value, count in Counter(str(e.get(key)) for e in events).most_common(15):
            print(f"{count:8}  {_d(value)}")
    return 0


def cmd_analytics(s: Session, args: argparse.Namespace) -> int:
    """Zone traffic as Cloudflare sees it (not a replacement for server logs)."""
    zone = s.zone(args.domain)
    zone_id = zone["id"]
    until = datetime.now(UTC)
    since = parse_since(args.since, until)  # one clock reading: 24h is exactly one day
    print(f"=== {_d(zone.get('name'))} - traffic since {since.strftime('%Y-%m-%d %H:%M')} UTC ===")
    if until - since > timedelta(days=1):
        # adaptive groups allow a 1-day window on the free plan; the daily dataset is longer
        variables = {"zoneTag": zone_id, "since": since.strftime("%Y-%m-%d"),
                     "until": until.strftime("%Y-%m-%d"), "limit": args.limit}  # fmt: skip
        daily = s.graphql(GRAPHQL_TRAFFIC_DAILY, variables, "httpRequests1dGroups")
        if not daily:
            print("no data (longer windows use httpRequests1dGroups - check plan retention)")
            return 0

        def total(part: str, key: str) -> int:
            return sum(_int((row.get(part) or {}).get(key)) for row in daily)

        print("source: httpRequests1dGroups (daily totals, window longer than 1 day)")
        print(f"requests: {_num(total('sum', 'requests'))}")
        print(
            f"unique visitors: {_num(total('uniq', 'uniques'))}   (sum over days, not deduplicated)"
        )
        print(f"bytes:    {human_bytes(total('sum', 'bytes'))}")
        print(f"threats:  {_num(total('sum', 'threats'))}")
        print("--- by day ---")
        peak = max(_int((r.get("sum") or {}).get("requests")) for r in daily) or 1
        for row in daily:
            sums = row.get("sum") or {}
            req = _int(sums.get("requests"))
            date = _d((row.get("dimensions") or {}).get("date", "?"))
            cached = 100 * _int(sums.get("cachedRequests")) // max(req, 1)
            print(
                f"{date:12} {_num(req):>9} req  {_int(sums.get('pageViews')):7} views  "
                f"{_int((row.get('uniq') or {}).get('uniques')):6} uniq.  cache {cached:3} %  "
                + "#"
                * round(40 * req / peak)
            )
        return 0

    dimension = "datetimeHour"  # the adaptive dataset orders only by hour/minute
    variables = {"zoneTag": zone_id, "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "until": until.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": args.limit}  # fmt: skip
    rows = s.graphql(
        GRAPHQL_TRAFFIC.replace("__DIMENSION__", dimension), variables, "httpRequestsAdaptiveGroups"
    )
    if not rows:
        print("no data (check the --since window, retention depends on the plan)")
        return 0
    print(f"requests: {_num(sum(_int(r.get('count')) for r in rows))}")
    visits = sum(_int((r.get("sum") or {}).get("visits")) for r in rows)
    print(f"visits:   {_num(visits)}   (visits = entries from another site, not unique people)")
    print(
        "bytes:    "
        + human_bytes(sum(_int((r.get("sum") or {}).get("edgeResponseBytes")) for r in rows))
    )
    buckets: dict[str, list[int]] = {}
    for row in rows:
        stamp = str((row.get("dimensions") or {}).get(dimension, "?"))
        bucket = buckets.setdefault(stamp[:10] if args.by == "day" else stamp, [0, 0])
        bucket[0] += _int(row.get("count"))
        bucket[1] += _int((row.get("sum") or {}).get("visits"))
    print(f"--- by {args.by} ---")
    peak = max(value[0] for value in buckets.values()) or 1
    for key in sorted(buckets):
        req, vis = buckets[key]
        print(f"{_d(key):20} {_num(req):>9} req  {vis:7} visits  " + "#" * round(40 * req / peak))
    if args.no_breakdown:
        return 0
    variables["limit"] = 15
    for label, dim in (("country", "clientCountryName"), ("HTTP status", "edgeResponseStatus"),
                       ("cache", "cacheStatus")):  # fmt: skip
        query = GRAPHQL_TRAFFIC_BREAKDOWN.replace("__DIMENSION__", dim)
        rows = s.graphql(query, variables, "httpRequestsAdaptiveGroups")
        if not rows:
            continue
        print(f"--- {label} ---")
        for row in rows:
            value = (row.get("dimensions") or {}).get(dim, "?")
            print(f"{_num(_int(row.get('count'))):>9}  {_d(value)}")
    return 0


def _export_path(s: Session, domain: str, override: str | None) -> Path:
    if override:
        return Path(override)  # CLI path: from the CWD
    return _in_dir(s.export_dir, export_name(domain))


def cmd_export(s: Session, args: argparse.Namespace) -> int:
    path = _export_path(s, args.domain, args.output)
    state = s.state(args.domain)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RunError(f"cannot create {_d(path.parent)}: {e.strerror}") from None
    _write(path, json_text(state) + "\n")
    print(f"EXPORT {args.domain} -> {_d(path)}")
    print(
        f"  waf={len(state['waf_custom_rules'])} ratelimit={len(state['ratelimit_rules'])} "
        f"config={len(state['config_rules'])} access={len(state['ip_access_rules'])} "
        f"ua={len(state['user_agent_rules'])} dns={len(state['dns_records'])}"
    )
    return 0


def stable_json(payload: Any) -> str:
    """JSON without the timestamp, for comparing states."""
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k != "exported_at"}
    return json_text(payload)


def cmd_diff(s: Session, args: argparse.Namespace) -> int:
    path = _export_path(s, args.domain, args.input)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RunError(
            f"stored export {_d(path)} not found - run `cca cloudflare export {args.domain}` first"
        ) from None
    except (OSError, ValueError) as e:
        raise RunError(f"cannot read {_d(path)}: {_d(e)}") from None
    live = s.state(args.domain)
    diff = list(
        difflib.unified_diff(
            stable_json(stored).splitlines(), stable_json(live).splitlines(),
            fromfile=_d(path), tofile=f"live:{args.domain}", lineterm="",
        )
    )  # fmt: skip
    if not diff:
        print(f"OK {args.domain} - no change against {_d(path)}")
        return 0
    for line in diff:
        print(line)
    return 1


# ---------------------------------------------------------------- DNS writes


@dataclass(frozen=True)
class DesiredRecord:
    name: str
    type: str
    content: str
    ttl: int = 1
    proxied: bool = False


def ensure_record(s: Session, zone: dict, desired: DesiredRecord, apply: bool) -> bool:
    existing = s.records(zone["id"], desired.name)
    same_type = [r for r in existing if r.get("type") == desired.type]
    conflicts = [r for r in existing if r.get("type") != desired.type]
    if conflicts or len(same_type) > 1:
        print(f"CONFLICT {desired.name}")
        if not conflicts:
            print("  existing: more than one record of this type")
        for record in conflicts or same_type:
            print(f"  existing: {format_record(record)}")
        return False
    payload = {"zone_id": zone["id"], "name": desired.name, "type": desired.type,
               "content": desired.content, "ttl": desired.ttl,
               "proxied": desired.proxied}  # fmt: skip
    if not same_type:
        print(f"CREATE {desired.name} -> {desired.content}")
        if apply:
            s.client.dns.records.create(**payload)
        return True
    current = same_type[0]
    if (
        normalize_content(current.get("content", "")) == normalize_content(desired.content)
        and _int(current.get("ttl")) == desired.ttl
        and bool(current.get("proxied", False)) == desired.proxied
    ):
        print(f"OK {desired.name} -> {desired.content}")
        return True
    print(f"UPDATE {desired.name}")
    print(f"  from: {format_record(current)}")
    print(
        f"  to:   {desired.name} {desired.type} {normalize_content(desired.content)} "
        f"ttl={desired.ttl} proxied={str(desired.proxied).lower()}"
    )
    if apply:
        s.client.dns.records.edit(api_id(current.get("id"), "record"), **payload)
    return True


def cmd_ensure_dkim(s: Session, args: argparse.Namespace) -> int:
    print("MODE:", "apply" if args.apply else "plan")
    ok = True
    for index, domain in enumerate(args.domains):
        if index:
            print()
        zone = s.zone(domain)
        zone_name = str(zone.get("name")).lower()
        print(f"=== {zone_name} ===")
        for selector in args.selector:
            desired = DesiredRecord(
                f"{selector}._domainkey.{zone_name}", "CNAME",
                f"{selector}._domainkey.{args.target_domain}",
            )  # fmt: skip
            ok = ensure_record(s, zone, desired, args.apply) and ok
    if not args.apply:
        print(PLAN_END)
    return 0 if ok else 1


def cmd_ensure_cname(s: Session, args: argparse.Namespace) -> int:
    print("MODE:", "apply" if args.apply else "plan")
    zone = s.zone(args.domain)
    zone_name = str(zone.get("name")).lower()
    print(f"=== {zone_name} ===")
    ok = ensure_record(
        s, zone, DesiredRecord(fqdn(args.name, zone_name), "CNAME", args.target), args.apply
    )
    if not args.apply:
        print(PLAN_END)
    return 0 if ok else 1


def record_match_key(record: dict) -> tuple:
    return (
        record.get("name", ""),
        record.get("type", ""),
        normalize_content(record.get("content", "")),
    )


def record_payload_equal(current: dict, desired: dict) -> bool:
    return all(
        (current.get(f) or 0) == (desired.get(f) or 0) for f in ("ttl", "proxied", "priority")
    )


def cmd_restore_zone(s: Session, args: argparse.Namespace) -> int:
    path = Path(args.input)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RunError(f"input file {_d(path)} not found") from None
    except (OSError, ValueError) as e:
        raise RunError(f"cannot read {_d(path)}: {_d(e)}") from None
    if not isinstance(payload, dict) or payload.get("schema") != "cloudflare-dns-dump/1":
        raise RunError("unknown schema, expected cloudflare-dns-dump/1")
    desired_records = payload.get("records") or []
    if not isinstance(desired_records, list) or not all(
        isinstance(r, dict) for r in desired_records
    ):
        raise RunError("records must be a list of objects")
    domain = args.domain
    if domain is None:
        file_zone = (
            (payload.get("zone") or {}).get("name")
            if isinstance(payload.get("zone"), dict)
            else None
        )
        domain = validate.dns_name(file_zone) if isinstance(file_zone, str) else None
        if domain is None:
            raise RunError("no valid zone name in the file; use --domain")
    zone = s.zone(domain)
    zone_id = zone["id"]
    existing = [
        record_to_dict(r) | {"_id": api_id(r.get("id"), "record")} for r in s.records(zone_id)
    ]
    by_key: dict[tuple, list[dict]] = {}
    for record in existing:
        by_key.setdefault(record_match_key(record), []).append(record)

    print("MODE:", "apply" if args.apply else "plan")
    print(f"=== {_d(zone.get('name'))} restore ({len(desired_records)} records) ===")
    handled: set[str] = set()
    create_n = update_n = ok_n = delete_n = kept_n = 0
    for desired in desired_records:
        fields = record_to_dict(desired)  # dump fields without nulls
        candidates = by_key.get(record_match_key(desired), [])
        if not candidates:
            print(
                f"CREATE {_d(desired.get('name'))} {_d(desired.get('type'))} "
                f"-> {_d(desired.get('content'))}"
            )
            create_n += 1
            if args.apply:
                s.client.dns.records.create(zone_id=zone_id, **fields)
            continue
        current = candidates.pop(0)
        handled.add(current["_id"])
        if record_payload_equal(current, desired):
            ok_n += 1
            continue
        print(f"UPDATE {_d(desired.get('name'))} {_d(desired.get('type'))}")
        print(f"  from ttl={_d(current.get('ttl'))} proxied={_d(current.get('proxied'))}")
        print(f"  to   ttl={_d(desired.get('ttl'))} proxied={_d(desired.get('proxied'))}")
        update_n += 1
        if args.apply:
            s.client.dns.records.edit(current["_id"], zone_id=zone_id, **fields)
    for record in existing:
        if record["_id"] in handled:
            continue
        if args.delete_extras:
            print(
                f"DELETE {_d(record.get('name'))} {_d(record.get('type'))} "
                f"-> {_d(record.get('content'))}"
            )
            delete_n += 1
            if args.apply:
                s.client.dns.records.delete(record["_id"], zone_id=zone_id)
        else:
            kept_n += 1
    print(
        f"--- create={create_n} update={update_n} ok={ok_n} delete={delete_n} "
        f"extras_kept={kept_n} ---"
    )
    if not args.apply:
        print(PLAN_END)
    return 0


# ---------------------------------------------------------------- WAF writes


@dataclass
class WafContext:
    session: Session
    domain: str
    zone_name: str
    zone_id: str
    account: dict
    phase: str
    label: str
    quota: int
    ruleset_id: str | None
    rules: list[dict]


def waf_context(s: Session, domain: str) -> WafContext:
    """One fresh snapshot of the phase: quota, targeting and placement come from it."""
    zone = s.zone(domain)
    phase, label, quota = PHASES["waf"]
    ruleset_id, rules = s.phase(zone["id"], phase)
    for rule in rules:
        api_id(rule.get("id"), "rule")
    account = zone.get("account") if isinstance(zone.get("account"), dict) else {}
    return WafContext(s, domain, str(zone.get("name")), zone["id"], account, phase, label,
                      quota, ruleset_id, rules)  # fmt: skip


def resolve_rule(rules: list[dict], selector: str, apply: bool, flag: str) -> tuple[int, dict]:
    """(1-based position, rule); a position is rejected with --apply (not stable)."""
    if API_ID_RE.fullmatch(selector.lower()):
        for index, rule in enumerate(rules, start=1):
            if str(rule.get("id") or "").lower() == selector.lower():
                return index, rule
        raise RunError(f"{flag}: no rule with id {selector} in this zone")
    if selector.isascii() and selector.isdigit():
        if apply:
            raise RunError(
                f"{flag}: a position cannot be used with --apply (the list may have changed "
                "since it was shown); use the rule id from `waf list`"
            )
        position = int(selector)
        if not 1 <= position <= len(rules):
            raise RunError(f"{flag}: position {position} is out of range 1-{len(rules)}")
        return position, rules[position - 1]
    matches = [
        (i, r) for i, r in enumerate(rules, start=1) if (r.get("description") or "") == selector
    ]
    if not matches:
        raise RunError(f"{flag}: no rule with description '{_d(selector)}'")
    if len(matches) > 1:
        listing = ", ".join(f"#{i} {r.get('id')}" for i, r in matches)
        raise RunError(
            f"{flag}: description '{_d(selector)}' matches several rules ({listing}); "
            "use the rule id"
        )
    return matches[0]


def resolve_placement(ctx: WafContext, args: argparse.Namespace) -> tuple[dict | None, str, tuple]:
    """(position payload, description, expected placement for the read-back)."""
    for flag, word in (("before", "right BEFORE"), ("after", "right AFTER")):
        selector = getattr(args, flag)
        if selector:
            index, rule = resolve_rule(ctx.rules, selector, args.apply, f"--{flag}")
            text = f"{word} #{index} {_d(rule.get('description') or rule['id'])}"
            return {flag: rule["id"]}, text, (flag, rule["id"])
    if args.position:
        if args.position > len(ctx.rules) + 1:
            raise RunError(f"--position: {args.position} is out of range 1-{len(ctx.rules) + 1}")
        return {"index": args.position}, f"at position {args.position}", ("index", args.position)
    return None, "at the end of the list", ("end", None)


def print_waf_header(ctx: WafContext, title: str) -> None:
    """Principal and target of the write: the token may see several accounts."""
    print(f"=== {title} ===")
    print(f"account:  {_d(ctx.account.get('name', '?'))} ({_d(ctx.account.get('id', '?'))})")
    print(f"zone:     {_d(ctx.zone_name)} ({ctx.zone_id})")
    print(f"phase:    {ctx.phase}")
    print(f"ruleset:  {ctx.ruleset_id or '(no zone entrypoint - it will be created)'}")


def render_rule_diff(current: dict | None, target: dict) -> list[str]:
    lines = []
    for field in ("description", "action", "expression", "enabled"):
        new = target.get(field)
        if current is None:
            lines.append(f"  {field}: {_d(new)}")
        elif current.get(field) == new:
            lines.append(f"  {field}: {_d(new)}  (unchanged)")
        else:
            lines.append(f"  {field}: {_d(current.get(field))}  ->  {_d(new)}")
    kept = {
        key: value
        for key, value in (current or {}).items()
        if key in ("action_parameters", "logging", "ratelimit", "ref") and value
    }
    if kept:
        lines.append(
            f"  kept unchanged: {_d(json.dumps(kept, ensure_ascii=False, sort_keys=True))}"
        )
    return lines


def pre_write_export(ctx: WafContext) -> Path:
    """Zone snapshot before a write; when it fails nothing is written."""
    import cloudflare

    try:
        directory = ctx.session.export_dir
        state = ctx.session.state(ctx.domain)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC)
        text = json_text(state) + "\n"
        for serial in range(1, 1000):  # a snapshot is never overwritten
            path = _in_dir(directory, snapshot_name(ctx.domain, stamp, serial))
            try:
                with open(path, "x", encoding="utf-8") as f:
                    f.write(text)
                break
            except FileExistsError:
                continue
        else:
            raise RunError("no free snapshot name")
    except (CcaError, OSError, cloudflare.APIError, LimitExceeded) as exc:
        detail = str(exc) if isinstance(exc, CcaError | LimitExceeded) else api_error(exc)
        raise RunError(
            f"pre-write export failed, nothing changed in Cloudflare: {detail}"
        ) from None
    print(f"pre-write export: {_d(path)}")
    return path


def check_placement(rules: list[dict], rule_id: str, expected: tuple) -> str | None:
    order = [r.get("id") for r in rules]
    index = order.index(rule_id) + 1
    mode, anchor = expected
    if mode in ("before", "after"):
        others = [i for i in order if i != rule_id]
        if anchor not in others:
            return f"order: anchor {anchor} is gone"
        want = others.index(anchor) + (1 if mode == "before" else 2)
        if index != want:
            return f"order: expected right {mode} {anchor} (#{want}), is #{index}"
        return None
    if mode == "index":
        return None if index == anchor else f"order: expected #{anchor}, is #{index}"
    if mode == "end":
        return (
            None if index == len(order) else f"order: expected the end (#{len(order)}), is #{index}"
        )
    return None


def verify_after_apply(
    ctx: WafContext, rule_id: str, expected: dict, placement: tuple | None
) -> None:
    """A successful API reply does not prove the order: always read the state back."""
    _, rules = ctx.session.phase(ctx.zone_id, ctx.phase)
    current = next((r for r in rules if r.get("id") == rule_id), None)
    if current is None:
        raise RunError(f"read-back: rule {rule_id} is not in the zone after the write")
    problems = [
        f"{field}: wrote {_d(repr(value))}, zone has {_d(repr(current.get(field)))}"
        for field, value in expected.items()
        if current.get(field) != value
    ]
    if placement is not None:
        mismatch = check_placement(rules, rule_id, placement)
        if mismatch:
            problems.append(mismatch)
    if problems:
        raise RunError("read-back does not match the write:\n  " + "\n  ".join(problems))
    index = [r.get("id") for r in rules].index(rule_id) + 1
    print(f"read-back OK: #{index} {rule_id}")


def prune_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: prune_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_nulls(v) for v in value]
    return value


def writable_payload(rule: dict) -> dict:
    """The rule without read-only fields: the base of an edit, so nothing is dropped."""
    return prune_nulls({k: v for k, v in rule.items() if k not in READONLY_RULE_FIELDS})


def _write_rule(call, *args: Any, **kwargs: Any) -> Any:
    try:
        return call(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise RunError(f"Cloudflare rejected the write: {api_error(exc)}") from None


def cmd_waf_add(s: Session, args: argparse.Namespace) -> int:
    ctx = waf_context(s, args.domain)
    if len(ctx.rules) >= ctx.quota:
        raise RunError(
            f"the zone has {len(ctx.rules)}/{ctx.quota} {ctx.label} (disabled rules count) - "
            "no room for a new rule"
        )
    position, placement_text, expected = resolve_placement(ctx, args)
    target = {"description": args.description, "action": args.action,
              "expression": args.expression, "enabled": not args.disabled}  # fmt: skip
    print_waf_header(ctx, f"waf add - {ctx.domain}")
    print(f"quota:    {len(ctx.rules)}/{ctx.quota} -> {len(ctx.rules) + 1}/{ctx.quota}")
    print(f"place:    {placement_text}")
    if position is None:
        print("  ! without --before/--after/--position the rule goes to the END. The order decides")
        print("    which rule applies first - check that this is intended.")
    print("--- new rule ---")
    for line in render_rule_diff(None, target):
        print(line)
    if not args.apply:
        print(PLAN_END)
        return 0
    pre_write_export(ctx)
    old_ids = {rule.get("id") for rule in ctx.rules}
    rulesets = s.client.rulesets
    if ctx.ruleset_id is None:
        response = _write_rule(rulesets.create, zone_id=ctx.zone_id, kind="zone",
                               phase=ctx.phase, name=ctx.label, rules=[target])  # fmt: skip
        print(f"created ruleset {_d(plain(response).get('id'))}")
    else:
        payload = dict(target, **({"position": position} if position else {}))
        _write_rule(rulesets.rules.create, ctx.ruleset_id, zone_id=ctx.zone_id, **payload)
    _, after = s.phase(ctx.zone_id, ctx.phase)
    created = [rule for rule in after if rule.get("id") not in old_ids]
    if len(created) != 1:
        raise RunError(f"read-back: cannot identify the new rule (found {len(created)})")
    verify_after_apply(ctx, api_id(created[0].get("id"), "rule"), target, expected)
    return 0


def cmd_waf_edit(s: Session, args: argparse.Namespace) -> int:
    ctx = waf_context(s, args.domain)
    if ctx.ruleset_id is None:
        raise RunError(f"zone {ctx.domain} has no {ctx.label} - nothing to edit")
    index, rule = resolve_rule(ctx.rules, args.rule, args.apply, "--rule")
    current = writable_payload(rule)
    target = dict(current)
    for field in ("description", "expression", "action"):
        if getattr(args, field) is not None:
            target[field] = getattr(args, field)
    if args.enable or args.disable:
        target["enabled"] = bool(args.enable)
    if (
        args.action is not None
        and args.action != rule.get("action")
        and rule.get("action_parameters")
    ):
        raise RunError(
            f"the rule has action '{_d(rule.get('action'))}' with action_parameters "
            f"{_d(json.dumps(rule['action_parameters'], ensure_ascii=False))}; changing the action "
            "would invalidate them - do it in the dashboard"
        )
    print_waf_header(ctx, f"waf edit - {ctx.domain}")
    print(f"rule:     #{index} {rule['id']}")
    print("--- change ---")
    for line in render_rule_diff(current, target):
        print(line)
    if target == current:
        print("Nothing to change.")
        return 0
    if not args.apply:
        print(PLAN_END)
        return 0
    pre_write_export(ctx)
    _write_rule(s.client.rulesets.rules.edit, rule["id"], ruleset_id=ctx.ruleset_id,
                zone_id=ctx.zone_id, **target)  # fmt: skip
    fields = ("description", "action", "expression", "enabled")
    verify_after_apply(ctx, rule["id"], {k: target[k] for k in fields if k in target}, None)
    return 0


def cmd_waf_move(s: Session, args: argparse.Namespace) -> int:
    ctx = waf_context(s, args.domain)
    if ctx.ruleset_id is None:
        raise RunError(f"zone {ctx.domain} has no {ctx.label} - nothing to move")
    index, rule = resolve_rule(ctx.rules, args.rule, args.apply, "--rule")
    position, placement_text, expected = resolve_placement(ctx, args)
    if rule["id"] in (position.get("before"), position.get("after")):
        raise RunError("the anchor is the rule being moved")
    print_waf_header(ctx, f"waf move - {ctx.domain}")
    print(
        f"rule:     #{index} {rule['id']} [{_d(rule.get('action'))}] "
        f"{_d(rule.get('description') or '')}"
    )
    print(f"place:    {placement_text}")
    print("--- current order ---")
    for order, item in enumerate(ctx.rules, start=1):
        mark = " <-" if item.get("id") == rule["id"] else ""
        print(
            f"  {order}. [{_d(item.get('action', '?'))}] "
            f"{_d(item.get('description') or item.get('id'))}{mark}"
        )
    if not args.apply:
        print(PLAN_END)
        return 0
    pre_write_export(ctx)
    payload = writable_payload(rule)
    _write_rule(s.client.rulesets.rules.edit, rule["id"], ruleset_id=ctx.ruleset_id,
                zone_id=ctx.zone_id, position=position, **payload)  # fmt: skip
    fields = ("action", "expression", "enabled")
    verify_after_apply(ctx, rule["id"], {k: payload[k] for k in fields if k in payload}, expected)
    return 0


# ---------------------------------------------------------------- dispatch

HANDLERS = {
    ("token", "verify"): cmd_token_verify,
    ("zone", "list"): cmd_zone_list,
    ("zone", "info"): cmd_zone_info,
    ("zone", "settings"): cmd_zone_settings,
    ("dns", "show-domain"): cmd_show_domain,
    ("dns", "show-dkim"): cmd_show_dkim,
    ("dns", "ensure-dkim"): cmd_ensure_dkim,
    ("dns", "ensure-cname"): cmd_ensure_cname,
    ("dns", "dump-zone"): cmd_dump_zone,
    ("dns", "restore-zone"): cmd_restore_zone,
    ("waf", "list"): cmd_rules_list,
    ("waf", "countries"): cmd_waf_countries,
    ("waf", "add"): cmd_waf_add,
    ("waf", "edit"): cmd_waf_edit,
    ("waf", "move"): cmd_waf_move,
    ("ratelimit", "list"): cmd_rules_list,
    ("config", "list"): cmd_rules_list,
    ("access", "list"): cmd_access_list,
    ("ua", "list"): cmd_ua_list,
    ("uam", "status"): cmd_uam_status,
    ("bots", "status"): cmd_bots_status,
    ("events", None): cmd_events,
    ("analytics", None): cmd_analytics,
    ("export", None): cmd_export,
    ("diff", None): cmd_diff,
}


def run(args: argparse.Namespace) -> int:
    key = (args.cf_group, args.cf_command)
    if key not in HANDLERS:
        print(args.cf_help(), file=sys.stderr, end="")
        return 2
    cfg = config.require(args.config)
    token = secrets.cloudflare_token(cfg)  # exit 2 when missing; never the environment
    import cloudflare

    session = Session(cfg, make_client(token, cfg.get("cloudflare.api_base")))
    try:
        return HANDLERS[key](session, args)
    except cloudflare.APIError as exc:
        raise RunError(api_error(exc)) from None
    except LimitExceeded as exc:
        raise RunError(str(exc)) from None
    finally:
        session.client.close()
