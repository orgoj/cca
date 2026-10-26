"""cca check-domain: options, output and exit codes.

A local UDP DNS server answers for *.test names (the module's NAMESERVER points at
it), local HTTP and HTTPS servers play the domains, the RDAP registry and the IANA
bootstrap (module PORTS, BOOTSTRAP); the HTTPS certificate is self-signed by `openssl`
and trusted through the module's CA_FILE.
"""

import shutil
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import dns.flags
import dns.message
import dns.rcode
import dns.rrset
import pytest

from cca.cli import main
from cca.commands import check_domain

NAMES = ["site.test", "alias.test", "other.test", "rdap.test", "iana.test", "v6.test"]
MARKER = ".hosting.txt"


class Dns:
    """Records by name: {"site.test.": [("A", "127.0.0.1")]}; names in `fail` SERVFAIL."""

    def __init__(self):
        self.records: dict[str, list[tuple[str, str]]] = {}
        self.fail: set[str] = set()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                wire, peer = self.sock.recvfrom(4096)
            except OSError:
                return
            query = dns.message.from_wire(wire)
            response = dns.message.make_response(query)
            response.flags |= dns.flags.RA
            question = query.question[0]
            name = question.name.to_text()
            rdtype = dns.rdatatype.to_text(question.rdtype)
            if name in self.fail:
                response.set_rcode(dns.rcode.SERVFAIL)
            elif not self.answer(response, name, rdtype):
                response.set_rcode(dns.rcode.NXDOMAIN)
            self.sock.sendto(response.to_wire(), peer)

    def answer(self, response, name: str, rdtype: str) -> bool:
        if name not in self.records:
            return False
        for kind, value in self.records[name]:
            if kind == "CNAME":
                response.answer.append(dns.rrset.from_text(name, 60, "IN", "CNAME", value))
                return self.answer(response, value, rdtype)
            if kind == rdtype:
                response.answer.append(dns.rrset.from_text(name, 60, "IN", kind, value))
        return True


class Web:
    """Routes by (scheme, host, path) to (status, headers, body); default 404."""

    def __init__(self):
        self.routes: dict[tuple[str, str, str], tuple[int, dict, bytes]] = {}
        self.requests: list[tuple[str, str, str]] = []

    def route(self, url: str, status: int = 200, body: bytes = b"", **headers: str):
        scheme, rest = url.split("://", 1)
        host, _, path = rest.partition("/")
        self.routes[(scheme, host, "/" + path)] = (status, headers, body)


def handler(web: Web, scheme: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").rsplit(":", 1)[0]
            web.requests.append((scheme, host, self.path))
            status, headers, body = web.routes.get(
                (scheme, host, self.path), (404, {}, b"not found")
            )
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


@pytest.fixture(scope="session")
def certificate(tmp_path_factory) -> tuple[Path, Path]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl not found")
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "cert.pem", directory / "key.pem"
    san = ",".join(f"DNS:{n}" for n in NAMES if n != "v6.test")  # v6.test: name mismatch
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1"]
        + ["-keyout", str(key), "-out", str(cert), "-subj", "/CN=site.test"]
        + ["-addext", f"subjectAltName={san}"],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.fixture
def env(monkeypatch, tmp_path, certificate):
    dns_server, web = Dns(), Web()
    plain = ThreadingHTTPServer(("127.0.0.1", 0), handler(web, "http"))
    secure = ThreadingHTTPServer(("127.0.0.1", 0), handler(web, "https"))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*map(str, certificate))
    secure.socket = context.wrap_socket(secure.socket, server_side=True)
    for server in (plain, secure):
        threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    ports = {"http": plain.server_address[1], "https": secure.server_address[1]}
    monkeypatch.setattr(check_domain, "NAMESERVER", ("127.0.0.1", dns_server.sock.getsockname()[1]))
    monkeypatch.setattr(check_domain, "PORTS", ports)
    monkeypatch.setattr(check_domain, "CA_FILE", str(certificate[0]))
    monkeypatch.setattr(check_domain, "BOOTSTRAP", "https://iana.test/rdap/")
    monkeypatch.setattr(check_domain, "TIMEOUT", 3)
    for name in NAMES:
        dns_server.records[name + "."] = [("A", "127.0.0.1")]
    web.route(
        "https://iana.test/rdap/ipv4.json",
        body=b'{"services": '
        b'[[["127.0.0.0/8"], ["https://wrong.test/"]],'  # longest prefix wins
        b' [["127.0.0.0/24"], 5], [["127.0.0.0/24"]], "junk",'  # malformed entries skipped
        b' [["127.0.0.0/16"], ["http://rdap.test/", "https://rdap.test/rdap/"]]]}',
    )
    web.route("https://iana.test/rdap/ipv6.json", body=b'{"services": []}')
    web.route("http://site.test/", 301, Location="https://site.test/")
    web.route("https://site.test/", body=b"home")
    monkeypatch.chdir(tmp_path)
    yield dns_server, web, tmp_path
    for server in (plain, secure):
        server.shutdown()
        server.server_close()
    dns_server.sock.close()


def write_config(directory: Path, our_ips: list[str] | None = None, marker: str | None = MARKER):
    lines = ["schema_version = 1", "[check_domain]"]
    if our_ips is not None:
        lines.append("our_ips = [" + ", ".join(f'"{ip}"' for ip in our_ips) + "]")
    if marker is not None:
        lines.append(f'hosting_marker = "/{marker}"')
    (directory / ".cca.toml").write_text("\n".join(lines) + "\n")


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(["check-domain", *argv])
    out, err = capsys.readouterr()
    return code, out, err


CLOUDFLARE = (
    b'{"name": "CLOUDFLARENET", "handle": "NET-1", "entities": ['
    b'{"roles": ["abuse"], "vcardArray": ["vcard", [["fn", {}, "text", "Abuse Desk"]]]},'
    b'{"roles": ["registrant"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"],'
    b' ["fn", {}, "text", "Cloudflare, Inc."]]]}]}'
)


def test_confirmed_on_our_address(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    web.route(f"https://site.test/{MARKER}", body=b"server1\n")
    code, out, err = run(capsys, "Site.Test.")
    assert code == 0
    assert out.splitlines() == [
        "Domain: site.test",
        "A: 127.0.0.1 (ours)",
        f"Marker: https://site.test/{MARKER}",
        "  certificate: valid",
        "Redirects from http://site.test/:",
        "  301 http://site.test/ -> https://site.test/ [HTTP->HTTPS]",
        "  200 https://site.test/",
        "Result: CONFIRMED (served by server1)",
    ]
    assert err == ""
    assert not any(host == "rdap.test" for _s, host, _p in web.requests)


def test_foreign_address_owner_and_cdn(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["192.0.2.1"])
    web.route("https://rdap.test/rdap/ip/127.0.0.1", body=CLOUDFLARE)
    web.route(f"https://site.test/{MARKER}", body=b"server1")
    code, out, _err = run(capsys, "site.test")
    assert code == 0
    assert "A: 127.0.0.1 - owner: CLOUDFLARENET (Cloudflare, Inc.) - CDN Cloudflare" in out


def test_rdap_failures_are_informational(env, capsys):
    dns_server, web, directory = env
    write_config(directory, [])
    dns_server.records["site.test."] = [("A", "127.0.0.1"), ("AAAA", "::1")]
    web.route("https://rdap.test/rdap/ip/127.0.0.1", 302, Location="http://rdap.test/x")
    web.route(f"https://site.test/{MARKER}", body=b"server1")
    code, out, err = run(capsys, "site.test")
    assert code == 0
    assert "A: 127.0.0.1 - owner: unknown (RDAP redirect to non-HTTPS http://rdap.test/x)" in out
    assert "AAAA: ::1 - owner: unknown (no RDAP service in the IANA bootstrap)" in out
    assert "our_ips is not set" in err


def test_rdap_falls_back_to_handle(env, capsys):
    _dns, web, directory = env
    write_config(directory, [])
    web.route("https://rdap.test/rdap/ip/127.0.0.1", body=b'{"handle": "NET-\\u001b[31m"}')
    run_code, out, _err = run(capsys, "site.test")
    assert run_code == 1
    assert "owner: NET-\\x1b[31m" in out
    assert "\x1b" not in out


def test_marker_redirect_same_host_is_followed(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    web.route(f"https://site.test/{MARKER}", 301, Location="/moved/marker")
    web.route("https://site.test/moved/marker", body=b"web2")
    code, out, _err = run(capsys, "site.test")
    assert code == 0
    assert f"  301 https://site.test/{MARKER} -> https://site.test/moved/marker" in out
    assert out.endswith("Result: CONFIRMED (served by web2)\n")


def test_marker_redirect_to_other_host_fails(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    web.route(f"https://site.test/{MARKER}", 302, Location=f"https://other.test/{MARKER}")
    web.route(f"https://other.test/{MARKER}", body=b"server1")
    code, out, _err = run(capsys, "site.test")
    assert code == 1
    assert out.endswith(
        f"Result: NOT CONFIRMED (redirect to another host: https://other.test/{MARKER})\n"
    )
    assert ("https", "other.test", f"/{MARKER}") not in web.requests


@pytest.mark.parametrize(
    ("status", "body", "reason"),
    [
        (404, b"", "HTTP 404"),
        (200, b"", "invalid marker content: "),
        (200, b"line1\nline2", "invalid marker content: line1\\nline2"),
        (200, b"\x1b[31mred", "invalid marker content: \\x1b[31mred"),
        (200, b"\xff", "marker is not UTF-8 text"),
        (200, b"x" * 2000, "marker larger than 1024 bytes"),
    ],
)
def test_marker_invalid(env, capsys, status, body, reason):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    web.route(f"https://site.test/{MARKER}", status, body)
    code, out, _err = run(capsys, "site.test")
    assert code == 1
    assert out.endswith(f"Result: NOT CONFIRMED ({reason})\n")
    assert "\x1b" not in out


def test_invalid_certificate_is_reported(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    web.route(f"https://v6.test/{MARKER}", body=b"server1")
    web.route("http://v6.test/", 301, Location="https://v6.test/")
    web.route("https://v6.test/", body=b"home")
    code, out, _err = run(capsys, "v6.test")
    assert code == 0
    assert "  certificate: invalid: Hostname mismatch" in out
    assert "  200 https://v6.test/ [certificate invalid: Hostname mismatch" in out


def test_cname_and_aaaa_only(env, capsys):
    dns_server, web, directory = env
    write_config(directory, ["::1", "127.0.0.1"])
    dns_server.records["alias.test."] = [("CNAME", "v6.test.")]
    dns_server.records["v6.test."] = [("AAAA", "::1")]
    code, out, _err = run(capsys, "alias.test")
    assert out.splitlines()[:3] == [
        "Domain: alias.test",
        "CNAME: alias.test -> v6.test",
        "AAAA: ::1 (ours)",
    ]
    assert code == 1  # nothing listens on ::1 for the marker


def test_no_records(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"])
    code, out, _err = run(capsys, "missing.test")
    assert code == 1
    assert out == "Domain: missing.test\nResult: NOT CONFIRMED (no A or AAAA records)\n"
    assert web.requests == []


def test_resolver_failure(env, capsys):
    dns_server, _web, directory = env
    write_config(directory, ["127.0.0.1"])
    dns_server.fail.add("site.test.")
    code, _out, err = run(capsys, "site.test")
    assert code == 2
    assert "cca: error: DNS A lookup of site.test failed" in err


def test_without_config(env, capsys):
    _dns, web, _directory = env
    web.route("https://rdap.test/rdap/ip/127.0.0.1", body=CLOUDFLARE)
    code, out, err = run(capsys, "site.test")
    assert code == 1
    assert "Marker: check_domain.hosting_marker is not configured" in out
    assert "our_ips is not set" in err
    assert ("https", "site.test", f"/{MARKER}") not in web.requests


def test_redirect_chain_escapes_and_stops(env, capsys):
    _dns, web, directory = env
    write_config(directory, ["127.0.0.1"], marker=None)
    web.route("http://other.test/", 302, Location="http://other.test/\x1b[2J")
    code, out, _err = run(capsys, "other.test")
    assert code == 1
    assert "  error: redirect to unsupported URL http://other.test/\\x1b[2J" in out
    for n in range(7):
        web.route(f"http://site.test/{n}", 302, Location=f"/{n + 1}")
    web.route("http://site.test/", 302, Location="/0")
    _code, out, _err = run(capsys, "site.test")
    assert "  more than 5 redirects" in out


def test_invalid_domain(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["check-domain", "bad_name!"])
    assert exc.value.code == 2
    assert "invalid domain 'bad_name!'" in capsys.readouterr().err
