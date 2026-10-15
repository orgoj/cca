"""cca check-domain: does a domain point to our hosting?

DNS (A, AAAA, CNAME chain), the owner of each address that is not ours (RDAP), the
hosting marker file served for the domain, and the redirect chain of http://DOMAIN/.
Every HTTP request connects to addresses from the same resolver, so one run sees one
DNS view; nothing is taken from proxy settings in the environment.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import socket
import ssl
import sys
import threading
import urllib.parse
from dataclasses import dataclass
from typing import Any

import dns.exception
import dns.name
import dns.resolver

from cca import config, validate
from cca.output import CcaError, warn

NAMESERVER: tuple[str, int] | None = None  # tests point the resolver at a local server
PORTS = {"http": 80, "https": 443}  # default ports; tests point them at local servers
CA_FILE: str | None = None  # extra trust anchor for tests; None = system store
BOOTSTRAP = "https://data.iana.org/rdap/"  # IANA RDAP bootstrap registry
DNS_LIFETIME = 5
TIMEOUT = 10  # socket timeout of one request
SLACK = 5  # added for the whole request (slow headers, trickled body)
MAX_REDIRECTS = 5
MAX_RDAP_REDIRECTS = 3
MARKER_MAX = 1024  # marker body cap; the content is one short line
MARKER_LINE_MAX = 100
RDAP_MAX = 1024 * 1024
BOOTSTRAP_MAX = 4 * 1024 * 1024
REDIRECT_CODES = (301, 302, 303, 307, 308)
CDN_NAMES = (  # lowercase part of an RDAP network or organization name -> CDN
    ("cloudflare", "Cloudflare"),
    ("fastly", "Fastly"),
    ("akamai", "Akamai"),
    ("amazon-cf", "CloudFront"),
    ("cloudfront", "CloudFront"),
    ("cdn77", "CDN77"),
    ("bunny", "BunnyCDN"),
)

EPILOG = """\
Settings from [check_domain] in .cca.toml: our_ips (addresses of our servers) and
hosting_marker (URL path of the file our web servers answer with their server name).

Exit status: 0 the marker confirms our hosting; 1 not confirmed (no address records,
marker missing, invalid, behind a redirect to another host, or not configured);
2 usage, configuration or DNS resolver error.
"""


class FetchError(Exception):
    """A request failed; the message never repeats response bytes unescaped."""


@dataclass
class Reply:
    url: str
    status: int
    location: str | None
    body: bytes
    cert_error: str | None  # https: why the certificate did not verify; None = valid


# --- DNS


def _resolver() -> dns.resolver.Resolver:
    if NAMESERVER is None:
        try:
            return dns.resolver.Resolver()
        except dns.exception.DNSException as e:
            raise CcaError(f"no DNS resolver configuration: {e}") from None
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [NAMESERVER[0]]
    resolver.port = NAMESERVER[1]
    return resolver


def _query(name: str, rdtype: str) -> dns.resolver.Answer | None:
    """The answer (None for NXDOMAIN); CcaError when the resolver fails."""
    try:
        return _resolver().resolve(
            dns.name.from_text(name),
            rdtype,
            raise_on_no_answer=False,
            lifetime=DNS_LIFETIME,
            search=False,
        )
    except dns.resolver.NXDOMAIN:
        return None
    except dns.exception.DNSException as e:
        raise CcaError(f"DNS {rdtype} lookup of {name} failed: {e}") from None


def lookup(name: str) -> tuple[list[tuple[str, str]], list[str]]:
    """(CNAME steps as (from, to), addresses A first) of a DNS name."""
    cnames: list[tuple[str, str]] = []
    addresses: list[str] = []
    for rdtype in ("A", "AAAA"):
        answer = _query(name, rdtype)
        if answer is None:
            continue
        if not cnames:
            for rrset in answer.chaining_result.cnames:
                for rdata in rrset:
                    cnames.append((_text(rrset.name), _text(rdata.target)))
        if answer.rrset is not None:
            addresses += [ipaddress.ip_address(r.address).compressed for r in answer.rrset]
    return cnames, addresses


def _text(name: dns.name.Name) -> str:
    return validate.display(name.to_text(omit_final_dot=True))


# --- HTTP


def _connect(host: str, port: int) -> socket.socket:
    try:
        addresses = [ipaddress.ip_address(host.strip("[]")).compressed]
    except ValueError:
        addresses = lookup(host)[1]
    if not addresses:
        raise FetchError(f"{validate.display(host)} has no address records")
    last: OSError | None = None
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout=TIMEOUT)
        except OSError as e:
            last = e
    raise FetchError(f"cannot connect to {validate.display(host)}:{port}: {last}")


def _tls(host: str, port: int) -> tuple[socket.socket, str | None]:
    """A TLS socket and why the certificate did not verify (None = valid)."""
    hostname = host.strip("[]")
    context = ssl.create_default_context(cafile=CA_FILE)
    try:
        return context.wrap_socket(_connect(host, port), server_hostname=hostname), None
    except ssl.SSLCertVerificationError as e:
        reason = validate.display(e.verify_message or str(e))
    except (ssl.SSLError, OSError) as e:
        raise FetchError(f"TLS to {validate.display(host)}:{port} failed: {e}") from None
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    try:
        return unverified.wrap_socket(_connect(host, port), server_hostname=hostname), reason
    except (ssl.SSLError, OSError) as e:
        raise FetchError(f"TLS to {validate.display(host)}:{port} failed: {e}") from None


def _get(url: str, limit: int, outcome: list) -> None:
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port or PORTS.get(parts.scheme)
    except ValueError:
        outcome.append(FetchError(f"invalid URL {validate.display(url)}"))
        return
    if parts.scheme not in PORTS or not parts.hostname or port is None:
        outcome.append(FetchError(f"unsupported URL {validate.display(url)}"))
        return
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    cert_error = None
    sock = None
    try:
        if parts.scheme == "https":
            sock, cert_error = _tls(host, port)
        else:
            sock = _connect(host, port)
        connection = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        connection.sock = sock
        host_header = host if port == PORTS[parts.scheme] else f"{host}:{port}"
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection.request(
            "GET", path, headers={"Host": host_header, "User-Agent": "cca-check-domain"}
        )
        response = connection.getresponse()
        body = response.read(limit + 1)
    except FetchError as e:
        outcome.append(e)
        return
    except CcaError as e:  # resolver failure for the URL's host
        outcome.append(FetchError(str(e)))
        return
    except (OSError, ValueError, http.client.HTTPException) as e:
        outcome.append(FetchError(f"{validate.display(url)}: {validate.display(str(e))}"))
        return
    finally:
        if sock is not None:
            sock.close()
    location = response.getheader("Location")
    outcome.append(Reply(url, response.status, location, body, cert_error))


def fetch(url: str, limit: int) -> Reply:
    """One GET without redirects, under a whole-request deadline."""
    outcome: list = []
    worker = threading.Thread(target=_get, args=(url, limit, outcome), daemon=True)
    worker.start()
    worker.join(TIMEOUT + SLACK)
    if not outcome:  # abandoned, it stops at the socket timeout
        raise FetchError(f"{validate.display(url)}: timed out")
    if isinstance(outcome[0], FetchError):
        raise outcome[0]
    return outcome[0]


def _next_url(reply: Reply) -> str:
    if not reply.location:
        raise FetchError(f"HTTP {reply.status} without a Location header")
    target = urllib.parse.urljoin(reply.url, reply.location.strip())
    if validate.has_control(target) or urllib.parse.urlsplit(target).scheme not in PORTS:
        raise FetchError(f"redirect to unsupported URL {validate.display(target)}")
    return target


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


# --- RDAP


def _bootstrap(version: int, cache: dict[int, list]) -> list:
    if version not in cache:
        reply = fetch(urllib.parse.urljoin(BOOTSTRAP, f"ipv{version}.json"), BOOTSTRAP_MAX)
        services = _json(reply, BOOTSTRAP_MAX).get("services")
        if not isinstance(services, list):
            raise FetchError("IANA bootstrap has no services list")
        cache[version] = services
    return cache[version]


def _json(reply: Reply, limit: int) -> dict:
    if reply.status != 200:
        raise FetchError(f"HTTP {reply.status} from {validate.display(reply.url)}")
    if len(reply.body) > limit:
        raise FetchError(f"response larger than {limit} bytes")
    try:
        data = json.loads(reply.body.decode("utf-8"))
    except ValueError:
        raise FetchError("invalid JSON") from None
    if not isinstance(data, dict):
        raise FetchError("unexpected JSON (not an object)")
    return data


def _rdap_base(address: str, services: list) -> str:
    ip = ipaddress.ip_address(address)
    best: tuple[int, str] | None = None
    for service in services:
        if not (isinstance(service, list) and len(service) == 2):
            continue
        prefixes, urls = service
        if not isinstance(prefixes, list) or not isinstance(urls, list):
            continue
        https = [u for u in urls if isinstance(u, str) and u.startswith("https://")]
        if not https:
            continue
        for prefix in prefixes:
            try:
                network = ipaddress.ip_network(prefix)
            except (TypeError, ValueError):
                continue
            if ip in network and (best is None or network.prefixlen > best[0]):
                best = (network.prefixlen, https[0])
    if best is None:
        raise FetchError("no RDAP service in the IANA bootstrap")
    return best[1]


def owner(address: str, cache: dict[int, list]) -> str:
    """Network and organization of an address from RDAP, or "unknown (reason)"."""
    try:
        services = _bootstrap(ipaddress.ip_address(address).version, cache)
        url = _rdap_base(address, services).rstrip("/") + "/ip/" + address
        for _ in range(MAX_RDAP_REDIRECTS + 1):
            reply = fetch(url, RDAP_MAX)
            if reply.status not in REDIRECT_CODES:
                break
            url = _next_url(reply)
            if not url.startswith("https://"):
                raise FetchError(f"RDAP redirect to non-HTTPS {validate.display(url)}")
        else:
            raise FetchError(f"more than {MAX_RDAP_REDIRECTS} RDAP redirects")
        data = _json(reply, RDAP_MAX)
    except FetchError as e:
        return f"unknown ({e})"
    names = [_string(data.get("name")), _organization(data.get("entities"))]
    names = [n for n in names if n] or [_string(data.get("handle"))]
    names = [n for n in names if n]
    if not names:
        return "unknown (no name in the RDAP response)"
    text = names[0] + (f" ({names[1]})" if len(names) > 1 else "")
    found = " ".join(names).lower()
    cdn = next((label for key, label in CDN_NAMES if key in found), None)
    return text + (f" - CDN {cdn}" if cdn else "")


def _string(value: Any) -> str:
    return validate.display(value.strip()) if isinstance(value, str) else ""


def _organization(entities: Any) -> str:
    """The vCard fn of the registrant entity (else the first entity that has one)."""
    if not isinstance(entities, list):
        return ""
    found = ""
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = _vcard_fn(entity.get("vcardArray"))
        roles = entity.get("roles")
        if name and isinstance(roles, list) and "registrant" in roles:
            return name
        found = found or name
    return found


def _vcard_fn(vcard: Any) -> str:
    if not (isinstance(vcard, list) and len(vcard) == 2 and isinstance(vcard[1], list)):
        return ""
    for prop in vcard[1]:
        if isinstance(prop, list) and len(prop) == 4 and prop[0] == "fn":
            return _string(prop[3])
    return ""


# --- checks


def check_marker(domain: str, marker: str) -> tuple[bool, str]:
    """(confirmed, message); prints the steps. Redirects only to the same host."""
    url = f"https://{domain}/{marker}"
    print(f"Marker: {url}")
    certificate_shown = False
    for _ in range(MAX_REDIRECTS + 1):
        try:
            reply = fetch(url, MARKER_MAX)
            if reply.url.startswith("https://") and not certificate_shown:
                certificate_shown = True
                state = f"invalid: {reply.cert_error}" if reply.cert_error else "valid"
                print(f"  certificate: {state}")
            if reply.status not in REDIRECT_CODES:
                break
            target = _next_url(reply)
        except FetchError as e:
            return False, str(e)
        print(f"  {reply.status} {validate.display(url)} -> {validate.display(target)}")
        if _host(target) != domain:
            return False, f"redirect to another host: {validate.display(target)}"
        url = target
    else:
        return False, f"more than {MAX_REDIRECTS} redirects"
    if reply.status != 200:
        return False, f"HTTP {reply.status}"
    if len(reply.body) > MARKER_MAX:
        return False, f"marker larger than {MARKER_MAX} bytes"
    try:
        content = reply.body.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False, "marker is not UTF-8 text"
    if not content or len(content) > MARKER_LINE_MAX or not content.isprintable():
        return False, f"invalid marker content: {validate.display(content[:MARKER_LINE_MAX])}"
    return True, f"served by {content}"


def show_redirects(domain: str) -> None:
    url = f"http://{domain}/"
    print(f"Redirects from {url}:")
    for _ in range(MAX_REDIRECTS + 1):
        try:
            reply = fetch(url, 0)
            cert = f" [certificate invalid: {reply.cert_error}]" if reply.cert_error else ""
            if reply.status not in REDIRECT_CODES:
                print(f"  {reply.status} {validate.display(url)}{cert}")
                return
            target = _next_url(reply)
        except FetchError as e:
            print(f"  error: {e}")
            return
        scheme, new_scheme = url.split(":", 1)[0], target.split(":", 1)[0]
        change = f" [{scheme.upper()}->{new_scheme.upper()}]" if scheme != new_scheme else ""
        print(
            f"  {reply.status} {validate.display(url)} -> {validate.display(target)}{change}{cert}"
        )
        url = target
    print(f"  more than {MAX_REDIRECTS} redirects")


# --- command


def _domain(value: str) -> str:
    name = validate.dns_name(value)
    if name is None:
        raise argparse.ArgumentTypeError(f"invalid domain '{validate.display(value)}'")
    return name


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.description = (
        "Check whether DOMAIN points to our hosting: DNS records, owner of foreign "
        "addresses (RDAP), the hosting marker file and the redirect chain."
    )
    parser.epilog = EPILOG
    parser.add_argument("domain", metavar="DOMAIN", type=_domain, help="DNS name to check")


def run(args: argparse.Namespace) -> int:
    loaded = config.load(args.config)
    our_ips = (
        {ipaddress.ip_address(ip) for ip in loaded.get("check_domain.our_ips")} if loaded else set()
    )
    marker = loaded.get("check_domain.hosting_marker") if loaded else None
    if not our_ips:
        warn("check_domain.our_ips is not set in .cca.toml: cannot tell which addresses are ours")
    try:
        return _check(args.domain, our_ips, marker)
    except KeyboardInterrupt:
        return 130


def _check(domain: str, our_ips: set, marker: str | None) -> int:
    print(f"Domain: {domain}")
    cnames, addresses = lookup(domain)
    for source, target in cnames:
        print(f"CNAME: {source} -> {target}")
    if not addresses:
        print("Result: NOT CONFIRMED (no A or AAAA records)")
        return 1
    rdap_cache: dict[int, list] = {}
    for address in addresses:
        family = "AAAA" if ":" in address else "A"
        if ipaddress.ip_address(address) in our_ips:
            print(f"{family}: {address} (ours)")
        else:
            print(f"{family}: {address} - owner: {owner(address, rdap_cache)}")
        sys.stdout.flush()

    if marker is None:
        confirmed, message = False, "check_domain.hosting_marker is not configured"
        print(f"Marker: {message}")
    else:
        confirmed, message = check_marker(domain, marker.removeprefix("/"))
    sys.stdout.flush()
    show_redirects(domain)
    print(f"Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'} ({message})")
    return 0 if confirmed else 1
