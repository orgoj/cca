"""cca asn: routing, owner and type of IP addresses.

RIPEstat (announced prefix, origin ASNs and holder, RPKI validity, abuse contacts),
ipapi.is (organization, country, city and, with an API key, datacenter/proxy/VPN/Tor/
mobile/abuser/crawler/anycast flags) and the PTR record of each address. The optional
ipapi.is key is the bearer value of the project's curl credential for its origin
(doc-2 `secrets.curl`); it is sent only in a POST body, never in a URL.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import dns.exception
import dns.resolver
import dns.reversename

from cca import config, secrets, validate
from cca.output import CcaError, warn

RIPESTAT = "https://stat.ripe.net/data"  # tests point the API bases at a local server
IPAPI = "https://api.ipapi.is"
IPAPI_ORIGIN = "https://api.ipapi.is"  # origin of the key in the curl secrets file
NAMESERVER: tuple[str, int] | None = None  # tests point the PTR resolver at a local server
DNS_LIFETIME = 5
TIMEOUT = 10  # socket timeout of one request
SLACK = 5  # added for the whole request (slow headers, trickled body)
MAX_BODY = 1024 * 1024
FLAGS = (  # ipapi.is field -> short name
    ("is_datacenter", "dc"),
    ("is_proxy", "proxy"),
    ("is_vpn", "vpn"),
    ("is_tor", "tor"),
    ("is_mobile", "mobile"),
    ("is_abuser", "abuser"),
    ("is_crawler", "crawler"),
    ("is_anycast", "anycast"),
)

EPILOG = """\
Output: one line per address,
  IP|ASN|COUNTRY|FLAGS|rpki:STATUS|ORGANIZATION|PTR
ASN "AS-" when the address is not announced, several origins joined by "+"; FLAGS the
true ipapi.is type flags (dc, proxy, vpn, tor, mobile, abuser, crawler, anycast), "-"
none, "?" without an ipapi.is key; "-" a missing value, "?" a failed source. Non-global
addresses (private, loopback, reserved...) print "IP|bogon" without any lookup.
--json prints all fields as one JSON array instead.

ipapi.is key: the bearer value of the curl secrets credential for https://api.ipapi.is
in the project's .cca.toml [secrets]; without it the lookup is keyless (no type flags,
country name instead of code, 30 lookups a day).

Exit status: 0 every source answered; 1 a source failed for an address (named on
stderr); 2 usage or configuration error.
"""


class FetchError(Exception):
    """A lookup failed; the message is safe to print."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # the redirect response becomes an HTTP error


# --- HTTP


def fetch(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """JSON object from GET url (POST payload as JSON when given), strings escaped."""
    outcome: list = []
    worker = threading.Thread(target=_read, args=(url, payload, outcome), daemon=True)
    worker.start()
    worker.join(TIMEOUT + SLACK)
    if not outcome:  # still running: abandoned, it stops at the cap or the socket timeout
        raise FetchError("timed out")
    if isinstance(outcome[0], FetchError):
        raise outcome[0]
    status, body = outcome[0]
    if len(body) > MAX_BODY:
        raise FetchError(f"response larger than {MAX_BODY} bytes")
    try:
        data = json.loads(body.decode("utf-8"))
    except ValueError:  # includes UnicodeDecodeError
        data = None
    if status != 200:
        raise FetchError(f"HTTP {status}{_message(data)}")
    if not isinstance(data, dict):
        raise FetchError("invalid JSON (not an object)")
    return validate.clean(data)


def _read(url: str, payload: dict[str, Any] | None, outcome: list) -> None:
    # no proxy or other settings from the environment, no redirects
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            outcome.append((response.status, _read_capped(response)))
    except urllib.error.HTTPError as e:
        try:
            body = _read_capped(e)
        except (OSError, http.client.HTTPException, AttributeError):  # AttributeError: no fp
            body = b""
        outcome.append((e.code, body))
    except (OSError, http.client.HTTPException) as e:
        reason = getattr(e, "reason", None) or e
        outcome.append(FetchError(validate.display(str(reason))))


def _read_capped(stream: Any) -> bytes:
    body = bytearray()
    while len(body) <= MAX_BODY:
        chunk = stream.read1(65536)
        if not chunk:
            break
        body += chunk
    return bytes(body)


def _message(data: Any) -> str:
    """The API's error text (ipapi.is "error", RIPEstat "messages"), escaped and short."""
    if not isinstance(data, dict):
        return ""
    text = data.get("error")
    if not isinstance(text, str):
        messages = data.get("messages")
        parts = (
            [m[1] for m in messages if isinstance(m, list) and len(m) == 2]
            if isinstance(messages, list)
            else []
        )
        text = "; ".join(p for p in parts if isinstance(p, str))
    return f": {validate.display(text[:200])}" if text else ""


# --- sources


def ripestat(endpoint: str, **params: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({**params, "sourceapp": "cca"})
    reply = fetch(f"{RIPESTAT}/{endpoint}/data.json?{query}")
    if reply.get("status") != "ok" or not isinstance(reply.get("data"), dict):
        raise FetchError(f"{endpoint}: unexpected response{_message(reply)}")
    return reply["data"]


def routing(ip: str, result: dict[str, Any]) -> None:
    data = ripestat("prefix-overview", resource=ip)
    result["announced"] = data.get("announced") is True
    asns = []
    for entry in data.get("asns") or []:
        if isinstance(entry, dict) and type(entry.get("asn")) is int and entry["asn"] > 0:
            holder = entry.get("holder")
            asns.append(
                {"asn": entry["asn"], "holder": holder if isinstance(holder, str) else None}
            )
    result["asns"] = asns
    prefix = data.get("resource")
    try:
        result["prefix"] = ipaddress.ip_network(prefix).compressed if result["announced"] else None
    except (TypeError, ValueError):
        raise FetchError("prefix-overview: invalid prefix") from None


def rpki(result: dict[str, Any]) -> None:
    states = []
    for entry in result["asns"]:
        data = ripestat("rpki-validation", resource=str(entry["asn"]), prefix=result["prefix"])
        status = data.get("status")
        states.append({"asn": entry["asn"], "status": status if isinstance(status, str) else None})
    result["rpki"] = states


def abuse(ip: str, result: dict[str, Any]) -> None:
    data = ripestat("abuse-contact-finder", resource=ip)
    contacts = data.get("abuse_contacts")
    if not isinstance(contacts, list):
        raise FetchError("abuse-contact-finder: no abuse_contacts list")
    result["abuse_contacts"] = [c for c in contacts if isinstance(c, str)]


def ipapi(ip: str, key: str | None, result: dict[str, Any]) -> None:
    if key is None:
        data = fetch(f"{IPAPI}/?{urllib.parse.urlencode({'q': ip})}")
    else:
        data = fetch(f"{IPAPI}/", {"q": ip, "key": key})
    if "error" in data:
        raise FetchError(f"error{_message(data)}")
    company = data.get("company")
    if isinstance(company, dict):
        company = company.get("name")
    result["organization"] = company if isinstance(company, str) else None
    location = data.get("location")
    if isinstance(location, dict):  # keyed response
        result["country"] = _string(location.get("country_code"))
        result["city"] = _string(location.get("city"))
    else:  # keyless: country name, no code
        result["country"] = _string(data.get("country"))
        result["city"] = _string(data.get("city"))
    if key is not None:
        flags = {}
        for field, name in FLAGS:
            value = data.get(field)
            flags[name] = value if isinstance(value, (bool, str)) else None
        result["flags"] = flags


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _resolver() -> dns.resolver.Resolver:
    if NAMESERVER is None:
        try:
            return dns.resolver.Resolver()
        except dns.exception.DNSException as e:
            raise FetchError(f"no DNS resolver configuration: {e}") from None
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [NAMESERVER[0]]
    resolver.port = NAMESERVER[1]
    return resolver


def reverse(ip: str, result: dict[str, Any]) -> None:
    try:
        answer = _resolver().resolve(
            dns.reversename.from_address(ip), "PTR", raise_on_no_answer=False, lifetime=DNS_LIFETIME
        )
    except dns.resolver.NXDOMAIN:
        return
    except dns.exception.DNSException as e:
        raise FetchError(validate.display(str(e))) from None
    if answer.rrset:
        result["reverse"] = validate.display(answer.rrset[0].target.to_text(omit_final_dot=True))


# --- command


def lookup(ip: str, key: str | None, full: bool) -> dict[str, Any]:
    """All fields of one address; abuse contacts only when `full` (--json)."""
    result: dict[str, Any] = {"ip": ip, "bogon": not ipaddress.ip_address(ip).is_global}
    if result["bogon"]:
        return result
    result.update(
        reverse=None,
        announced=None,
        prefix=None,
        asns=None,
        rpki=None,
        abuse_contacts=None,
        organization=None,
        country=None,
        city=None,
        flags=None,
        errors={},
    )
    steps = [
        ("ripestat", lambda: routing(ip, result)),
        ("rpki", lambda: rpki(result) if result["announced"] else None),
        ("abuse", lambda: abuse(ip, result) if full else None),
        ("ipapi", lambda: ipapi(ip, key, result)),
        ("reverse", lambda: reverse(ip, result)),
    ]
    for source, step in steps:
        if source == "rpki" and "ripestat" in result["errors"]:
            continue
        try:
            step()
        except FetchError as e:
            result["errors"][source] = str(e) + _hint(source, str(e))
    return result


def _hint(source: str, reason: str) -> str:
    if source != "ipapi":
        return ""
    if reason.startswith("HTTP 429"):
        return " (ipapi.is daily quota used up)"
    if reason.startswith("HTTP 403"):
        return " (check the ipapi.is key in the curl secrets file)"
    return ""


def short(result: dict[str, Any]) -> str:
    if result["bogon"]:
        return f"{result['ip']}|bogon"
    errors = result["errors"]

    def value(text: str | None, *sources: str) -> str:
        """text, "-" when missing, "?" when it is missing because a source failed."""
        return text or ("?" if errors.keys() & set(sources) else "-")

    asns = result["asns"] or []
    asn = "+".join(f"AS{a['asn']}" for a in asns) or (
        "AS-" if result["announced"] is False else None
    )
    flags = result["flags"]
    flag_text = "?" if flags is None else ",".join(n for n, on in flags.items() if on) or "-"
    rpki_text = "+".join(s["status"] or "-" for s in result["rpki"] or [])
    holders = [a["holder"] for a in asns if a["holder"]]
    organization = result["organization"] or (holders[0] if holders else None)
    fields = [
        result["ip"],
        value(asn, "ripestat"),
        value(result["country"], "ipapi"),
        flag_text,
        "rpki:" + value(rpki_text, "ripestat", "rpki"),
        value(organization, "ipapi", "ripestat"),
        value(result["reverse"], "reverse"),
    ]
    return "|".join(f.replace("|", "/") for f in fields)


def _address(value: str) -> str:
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid IP address '{validate.display(value)}'"
        ) from None


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.description = (
        "Routing (RIPEstat: ASN, prefix, RPKI, abuse contacts), owner, country and type "
        "(ipapi.is) and PTR record of IP addresses."
    )
    parser.epilog = EPILOG
    parser.add_argument("--json", action="store_true", help="print all fields as JSON")
    parser.add_argument("ips", metavar="IP", nargs="+", type=_address, help="IPv4 or IPv6 address")


def ipapi_key(config_arg: str | None) -> str | None:
    """The bearer value of the curl credential for the ipapi.is origin, if configured."""
    cfg = config.load(config_arg)
    path = cfg.resolve(cfg.data["secrets"]["curl"]) if cfg else None
    if path is None or not path.exists():
        warn("no curl secrets file: ipapi.is keyless, IP type flags unavailable")
        return None
    origin, _tail = validate.parse_https_url(IPAPI_ORIGIN)
    matches = [c for c in secrets.curl_credentials(cfg).values() if origin in c.origins]
    if not matches:
        warn(f"no credential for {IPAPI_ORIGIN}: ipapi.is keyless, IP type flags unavailable")
        return None
    if len(matches) > 1:
        raise CcaError(f"several credentials in the curl secrets file allow {IPAPI_ORIGIN}")
    if matches[0].bearer is None:
        raise CcaError(f"credential '{matches[0].id}' for {IPAPI_ORIGIN} must be a bearer token")
    return matches[0].bearer


def run(args: argparse.Namespace) -> int:
    key = None
    if any(ipaddress.ip_address(ip).is_global for ip in args.ips):
        key = ipapi_key(args.config)
    results = []
    try:
        for ip in args.ips:
            result = lookup(ip, key, args.json)
            results.append(result)
            for source, reason in result.get("errors", {}).items():
                print(f"cca: {ip}: {source}: {reason}", file=sys.stderr)
            if not args.json:
                print(short(result), flush=True)
    except KeyboardInterrupt:
        return 130
    if args.json:
        print(json.dumps(results, indent=2))
    return 1 if any(r.get("errors") for r in results) else 0
