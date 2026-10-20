"""cca asn: routing, owner and type of IP addresses.

RIPEstat (announced prefix, origin ASNs and holder, RPKI validity, abuse contacts),
RDAP of the regional internet registries (the registered range of the address),
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
import time
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
# (origin, path prefix, rir) of the RIR RDAP services; the first is asked, a redirect is
# followed only to one of them and only for the same address
RDAP = [
    ("https://rdap.db.ripe.net", "/ip/", "ripe"),
    ("https://rdap.arin.net", "/registry/ip/", "arin"),
    ("https://rdap.apnic.net", "/ip/", "apnic"),
    ("https://rdap.lacnic.net", "/rdap/ip/", "lacnic"),
    ("https://rdap.afrinic.net", "/rdap/ip/", "afrinic"),
    ("https://rdap.registro.br", "/ip/", "nic.br"),  # LACNIC delegates Brazil to NIC.br
]
RDAP_ACCEPT = "application/rdap+json, application/json;q=0.9"  # LACNIC: 406 for json only
RDAP_HOPS = 2
REDIRECTS = (301, 302, 303, 307, 308)
QUOTA = "keyless daily quota used up"
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
  IP|ASN|COUNTRY|FLAGS|rpki:STATUS|ORGANIZATION|PTR|net:CIDRS
ASN "AS-" when the address is not announced, several origins joined by "+"; FLAGS the
true ipapi.is type flags (dc, proxy, vpn, tor, mobile, abuser, crawler, anycast), "-"
none, "?" without an ipapi.is key; net the range registered for the address at its
regional registry (RDAP inetnum/inet6num, as CIDRs joined by "+"), not the announced
prefix; "-" a missing value, "?" a failed source. Non-global addresses (private,
loopback, reserved...) print "IP|bogon" without any lookup. --json prints all fields
as one JSON array instead (registry range under "registry").

ipapi.is key: the bearer value of the curl secrets credential for https://api.ipapi.is
in the project's .cca.toml [secrets]; without it the lookup is keyless (no type flags,
country name instead of code, a small daily quota). When the keyless quota is used up,
one warning says so and the remaining addresses skip ipapi.is (country "?", organization
from the ASN holder); that alone does not change the exit status.

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
    status, body, _location = _exchange(url, payload, TIMEOUT + SLACK)
    return _decode(status, body)


def _exchange(
    url: str, payload: dict[str, Any] | None, wait: float, accept: str = "application/json"
) -> tuple[int, bytes, str | None]:
    """Status, body and Location header of one request that may take at most wait s."""
    outcome: list = []
    worker = threading.Thread(target=_read, args=(url, payload, outcome, accept), daemon=True)
    worker.start()
    worker.join(wait)
    if not outcome:  # still running: abandoned, it stops at the cap or the socket timeout
        raise FetchError("timed out")
    if isinstance(outcome[0], FetchError):
        raise outcome[0]
    return outcome[0]


def _decode(status: int, body: bytes) -> dict[str, Any]:
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


def _read(url: str, payload: dict[str, Any] | None, outcome: list, accept: str) -> None:
    # no proxy or other settings from the environment, no redirects
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    headers = {"Accept": accept}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            outcome.append((response.status, _read_capped(response), None))
    except urllib.error.HTTPError as e:
        try:
            body = _read_capped(e)
        except (OSError, http.client.HTTPException, AttributeError):  # AttributeError: no fp
            body = b""
        location = e.headers.get("Location") if e.headers is not None else None
        outcome.append((e.code, body, location))
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


def rdap(ip: str, result: dict[str, Any]) -> None:
    """The registered range from RIR RDAP; one deadline covers the whole redirect chain."""
    deadline = time.monotonic() + TIMEOUT + SLACK
    origin, prefix, rir = RDAP[0]
    url = origin + prefix + ip
    for hop in range(RDAP_HOPS + 1):
        left = deadline - time.monotonic()
        if left <= 0:
            raise FetchError("timed out")
        status, body, location = _exchange(url, None, left, RDAP_ACCEPT)
        if status not in REDIRECTS:
            result["registry"] = _registry(_decode(status, body), ip, rir)
            return
        if hop == RDAP_HOPS:
            raise FetchError("too many redirects")
        if not location:
            raise FetchError("redirect without location")
        url, rir = _rdap_redirect(location, ip)


def _rdap_redirect(location: str, ip: str) -> tuple[str, str]:
    """The URL (rebuilt from the table) and rir of an allowed redirect, else FetchError."""
    refused = FetchError(f"redirect to '{validate.display(location[:200])}' not allowed")
    parts = urllib.parse.urlsplit(location)
    try:
        port = parts.port
    except ValueError:
        raise refused from None
    if (
        parts.username is not None
        or parts.password is not None
        or "@" in parts.netloc
        or parts.query
        or parts.fragment
        or not parts.hostname
    ):
        raise refused
    default = {"https": 443, "http": 80}.get(parts.scheme)
    origin = f"{parts.scheme}://{parts.hostname}" + ("" if port in (None, default) else f":{port}")
    for allowed, prefix, rir in RDAP:
        if origin != allowed or not parts.path.startswith(prefix):
            continue
        try:
            same = ipaddress.ip_address(
                urllib.parse.unquote(parts.path[len(prefix) :])
            ) == ipaddress.ip_address(ip)
        except ValueError:
            same = False
        if same:
            return allowed + prefix + ip, rir
    raise refused


def _registry(data: dict[str, Any], ip: str, rir: str) -> dict[str, Any]:
    address = ipaddress.ip_address(ip)
    if not all(isinstance(data.get(k), str) for k in ("startAddress", "endAddress")):
        raise FetchError("invalid range")  # an int would parse as an address
    try:
        start = ipaddress.ip_address(data.get("startAddress"))
        end = ipaddress.ip_address(data.get("endAddress"))
    except ValueError:
        raise FetchError("invalid range") from None
    if start.version != address.version or end.version != address.version:
        raise FetchError("invalid range")
    if not start <= address <= end:
        raise FetchError("invalid range")
    return {
        "range": f"{start.compressed} - {end.compressed}",
        "cidrs": [n.compressed for n in ipaddress.summarize_address_range(start, end)],
        "name": _string(data.get("name")),
        "handle": _string(data.get("handle")),
        "type": _string(data.get("type")),
        "rir": rir,
    }


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


def lookup(ip: str, key: str | None, full: bool, quota_used: bool = False) -> dict[str, Any]:
    """All fields of one address; abuse contacts only when `full` (--json).

    quota_used: the keyless ipapi.is quota ran out earlier in this run, ipapi.is is skipped.
    """
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
        registry=None,
        errors={},
        skipped={},
    )
    steps = [
        ("ripestat", lambda: routing(ip, result)),
        ("rpki", lambda: rpki(result) if result["announced"] else None),
        ("abuse", lambda: abuse(ip, result) if full else None),
        ("rdap", lambda: rdap(ip, result)),
        ("ipapi", lambda: ipapi(ip, key, result)),
        ("reverse", lambda: reverse(ip, result)),
    ]
    for source, step in steps:
        if source == "rpki" and "ripestat" in result["errors"]:
            continue
        if source == "ipapi" and quota_used:
            result["skipped"]["ipapi"] = QUOTA
            continue
        try:
            step()
        except FetchError as e:
            if source == "ipapi" and key is None and str(e).startswith("HTTP 429"):
                result["skipped"]["ipapi"] = QUOTA  # not a failure: degrade, see EPILOG
                continue
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
    failed = result["errors"].keys() | result["skipped"].keys()

    def value(text: str | None, *sources: str) -> str:
        """text, "-" when missing, "?" when it is missing because a source failed."""
        return text or ("?" if failed & set(sources) else "-")

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
        # a skipped ipapi.is is no failure here: the ASN holder is the real fallback
        organization or ("?" if result["errors"].keys() & {"ipapi", "ripestat"} else "-"),
        value(result["reverse"], "reverse"),
        "net:" + value("+".join((result["registry"] or {}).get("cidrs", [])), "rdap"),
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
    quota_used = False
    try:
        for ip in args.ips:
            result = lookup(ip, key, args.json, quota_used)
            results.append(result)
            if "ipapi" in result.get("skipped", {}) and not quota_used:
                quota_used = True
                warn(f"ipapi.is {QUOTA}: country and city unavailable")
            for source, reason in result.get("errors", {}).items():
                print(f"cca: {ip}: {source}: {reason}", file=sys.stderr)
            if not args.json:
                print(short(result), flush=True)
    except KeyboardInterrupt:
        return 130
    if args.json:
        print(json.dumps(results, indent=2))
    return 1 if any(r.get("errors") for r in results) else 0
