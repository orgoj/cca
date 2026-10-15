"""cca asn: options, output and exit codes.

One local HTTP server plays RIPEstat and ipapi.is (the module's RIPESTAT and IPAPI point
at it), a local UDP DNS server answers PTR queries (NAMESERVER); the ipapi.is key comes
from a fake `sops` on a PATH that holds only fake tools.
"""

import json
import socket
import stat
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import dns.flags
import dns.message
import dns.rcode
import dns.rdatatype
import dns.rrset
import pytest

from cca.cli import main
from cca.commands import asn

KEY = "ipapi-key-sentinel"
CREDENTIALS = {
    "credentials": {
        "ipapi": {"origins": ["https://api.ipapi.is"], "bearer": KEY},
        "other": {"origins": ["https://api.example.com"], "bearer": "other-token-sentinel"},
    }
}
IP = "1.1.1.1"
PTR = "1.1.1.1.in-addr.arpa."


def ripe(data: dict) -> dict:
    return {"status": "ok", "data": data}


def ipapi_full(**extra) -> dict:
    return {
        "ip": IP,
        "is_datacenter": True,
        "is_proxy": False,
        "is_vpn": False,
        "is_tor": False,
        "is_mobile": False,
        "is_abuser": False,
        "is_crawler": False,
        "is_anycast": True,
        "company": {"name": "Example Org", "type": "hosting"},
        "location": {"country_code": "AU", "city": "Brisbane", "country": "Australia"},
        **extra,
    }


class Api:
    """Routes by path to a dict, a (status, body) tuple or "<slow>"; default 404."""

    def __init__(self):
        self.routes: dict = {
            "/data/prefix-overview/data.json": ripe(
                {
                    "announced": True,
                    "resource": "1.1.1.0/24",
                    "asns": [{"asn": 13335, "holder": "CLOUDFLARENET - Cloudflare, Inc."}],
                }
            ),
            "/data/rpki-validation/data.json": ripe({"status": "valid"}),
            "/data/abuse-contact-finder/data.json": ripe({"abuse_contacts": ["abuse@example.com"]}),
            "/ipapi/": ipapi_full(),
        }
        self.requests: list[tuple[str, str, dict, bytes]] = []

    def respond(self, method: str, path: str, query: dict, body: bytes):
        self.requests.append((method, path, query, body))
        route = self.routes.get(path)
        if route is None:
            return 404, json.dumps({"error": "not found"})
        if isinstance(route, tuple):
            return route
        if route == "<slow>":
            time.sleep(2)
            return 200, "{}"
        return 200, json.dumps(route)


class Dns:
    """PTR records by name; names in `fail` SERVFAIL, unknown names NXDOMAIN."""

    def __init__(self):
        self.records: dict[str, str] = {}
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
            name = query.question[0].name.to_text()
            if name in self.fail:
                response.set_rcode(dns.rcode.SERVFAIL)
            elif name in self.records:
                response.answer.append(
                    dns.rrset.from_text(name, 60, "IN", "PTR", self.records[name])
                )
            else:
                response.set_rcode(dns.rcode.NXDOMAIN)
            self.sock.sendto(response.to_wire(), peer)


@pytest.fixture
def api(monkeypatch):
    state = Api()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, method: str):
            url = urllib.parse.urlsplit(self.path)
            query = dict(urllib.parse.parse_qsl(url.query))
            length = int(self.headers.get("Content-Length") or 0)
            status, body = state.respond(method, url.path, query, self.rfile.read(length))
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/ipapi/elsewhere")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):  # noqa: N802
            self.reply("GET")

        def do_POST(self):  # noqa: N802
            self.reply("POST")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(asn, "RIPESTAT", base + "/data")
    monkeypatch.setattr(asn, "IPAPI", base + "/ipapi")
    yield state
    server.shutdown()
    server.server_close()


@pytest.fixture
def ptr(monkeypatch):
    server = Dns()
    server.records[PTR] = "one.example.net."
    monkeypatch.setattr(asn, "NAMESERVER", ("127.0.0.1", server.sock.getsockname()[1]))
    monkeypatch.setattr(asn, "DNS_LIFETIME", 2)
    yield server
    server.sock.close()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with .cca.toml and a sops file, fake sops, hostile env."""
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "curl.secret.yaml").write_text("credentials: ENC[...]\n")
    (tmp_path / "plain.json").write_text(json.dumps(CREDENTIALS))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sops = bindir / "sops"
    sops.write_text(f"#!/bin/sh\nexec /bin/cat {tmp_path / 'plain.json'}\n")
    sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # would fail every request if used
    monkeypatch.chdir(tmp_path)
    return tmp_path


def credentials(project: Path, creds: dict) -> None:
    (project / "plain.json").write_text(json.dumps({"credentials": creds}))


def cca(capsys, *argv: str) -> tuple[int, str, str]:
    try:
        code = main(["asn", *argv])
    except SystemExit as e:  # argparse errors
        code = e.code
    out, err = capsys.readouterr()
    assert KEY not in out and KEY not in err
    return code, out, err


# --- short output and sources


def test_short_line_with_key(project, api, ptr, capsys):
    code, out, err = cca(capsys, IP)
    assert (code, err) == (0, "")
    assert out == "1.1.1.1|AS13335|AU|dc,anycast|rpki:valid|Example Org|one.example.net\n"
    paths = [path for _m, path, _q, _b in api.requests]
    assert "/data/abuse-contact-finder/data.json" not in paths  # only for --json


def test_key_is_sent_only_in_the_post_body(project, api, ptr, capsys):
    cca(capsys, IP)
    method, _path, query, body = next(r for r in api.requests if r[1] == "/ipapi/")
    assert method == "POST" and query == {}
    assert json.loads(body) == {"q": IP, "key": KEY}
    for _m, path, query, _b in api.requests:
        assert KEY not in path and KEY not in json.dumps(query)


def test_ripestat_requests_name_the_resource_and_sourceapp(project, api, ptr, capsys):
    cca(capsys, IP)
    queries = {path: query for _m, path, query, _b in api.requests}
    assert queries["/data/prefix-overview/data.json"] == {"resource": IP, "sourceapp": "cca"}
    assert queries["/data/rpki-validation/data.json"] == {
        "resource": "13335",
        "prefix": "1.1.1.0/24",
        "sourceapp": "cca",
    }


def test_keyless_without_project_config(tmp_path, monkeypatch, api, ptr, capsys):
    monkeypatch.chdir(tmp_path)
    api.routes["/ipapi/"] = {
        "ip": IP,
        "company": "Keyless Org",
        "asn": "AS13335 Cloudflare, Inc.",
        "country": "Australia",
        "city": "Brisbane",
    }
    code, out, err = cca(capsys, IP)
    assert code == 0
    assert out == "1.1.1.1|AS13335|Australia|?|rpki:valid|Keyless Org|one.example.net\n"
    assert err.count("keyless") == 1
    method, _path, query, body = next(r for r in api.requests if r[1] == "/ipapi/")
    assert (method, query, body) == ("GET", {"q": IP}, b"")


def test_keyless_note_once_for_several_addresses(project, api, ptr, capsys):
    credentials(project, {"other": CREDENTIALS["credentials"]["other"]})
    code, out, err = cca(capsys, IP, "8.8.8.8")
    assert code == 0 and len(out.splitlines()) == 2
    assert err.count("keyless") == 1


def test_bogon_addresses_are_not_looked_up(project, api, ptr, capsys):
    code, out, err = cca(capsys, "192.168.1.1", "::1")
    assert (code, out, err) == (0, "192.168.1.1|bogon\n::1|bogon\n", "")
    assert api.requests == []


def test_not_announced(project, api, ptr, capsys):
    api.routes["/data/prefix-overview/data.json"] = ripe(
        {"announced": False, "resource": IP, "asns": []}
    )
    code, out, _ = cca(capsys, IP)
    assert code == 0
    assert out == "1.1.1.1|AS-|AU|dc,anycast|rpki:-|Example Org|one.example.net\n"
    assert "/data/rpki-validation/data.json" not in [p for _m, p, _q, _b in api.requests]


def test_several_origins_are_validated_each(project, api, ptr, capsys):
    api.routes["/data/prefix-overview/data.json"] = ripe(
        {
            "announced": True,
            "resource": "1.1.1.0/24",
            "asns": [{"asn": 64500, "holder": "A"}, {"asn": 64501, "holder": "B"}],
        }
    )
    _code, out, _ = cca(capsys, IP)
    assert out.startswith("1.1.1.1|AS64500+AS64501|AU|dc,anycast|rpki:valid+valid|")
    resources = [q["resource"] for _m, p, q, _b in api.requests if "rpki" in p]
    assert resources == ["64500", "64501"]


def test_missing_ptr_is_not_a_failure(project, api, ptr, capsys):
    ptr.records.clear()
    code, out, err = cca(capsys, IP)
    assert (code, err) == (0, "")
    assert out.endswith("|Example Org|-\n")


def test_hostile_strings_are_escaped_and_pipes_replaced(project, api, ptr, capsys):
    api.routes["/ipapi/"] = ipapi_full(company={"name": "Evil|Org\x1b[31m"})
    _code, out, _ = cca(capsys, IP)
    assert "\x1b" not in out
    assert "|Evil/Org\\x1b[31m|" in out


# --- failures


def test_failed_source_prints_question_mark_and_exits_1(project, api, ptr, capsys):
    api.routes["/ipapi/"] = (
        429,
        json.dumps({"error": "quota", "error_code": "ERR_QUOTA_EXCEEDED"}),
    )
    ptr.fail.add(PTR)
    code, out, err = cca(capsys, IP)
    assert code == 1
    assert out == "1.1.1.1|AS13335|?|?|rpki:valid|CLOUDFLARENET - Cloudflare, Inc.|?\n"
    assert "1.1.1.1: ipapi: HTTP 429: quota (ipapi.is daily quota used up)" in err
    assert "1.1.1.1: reverse:" in err


def test_ripestat_failure_skips_rpki(project, api, ptr, capsys):
    api.routes["/data/prefix-overview/data.json"] = (500, "oops")
    code, out, err = cca(capsys, IP)
    assert code == 1
    assert out == "1.1.1.1|?|AU|dc,anycast|rpki:?|Example Org|one.example.net\n"
    assert "ripestat: HTTP 500" in err


def test_ipapi_error_field_with_200_is_a_failure(project, api, ptr, capsys):
    api.routes["/ipapi/"] = {"error": "bad ip"}
    code, _out, err = cca(capsys, IP)
    assert code == 1 and "ipapi: error: bad ip" in err


def test_redirects_are_not_followed(project, api, ptr, capsys):
    api.routes["/ipapi/"] = (302, "")
    code, _out, err = cca(capsys, IP)
    assert code == 1 and "ipapi: HTTP 302" in err
    assert "/ipapi/elsewhere" not in [p for _m, p, _q, _b in api.requests]


def test_whole_request_deadline(project, api, ptr, capsys, monkeypatch):
    monkeypatch.setattr(asn, "TIMEOUT", 0.3)
    monkeypatch.setattr(asn, "SLACK", 0.2)
    api.routes["/ipapi/"] = "<slow>"
    code, _out, err = cca(capsys, IP)
    assert code == 1 and "ipapi: " in err


def test_body_cap(project, api, ptr, capsys, monkeypatch):
    monkeypatch.setattr(asn, "MAX_BODY", 100)
    api.routes["/ipapi/"] = ipapi_full(padding="x" * 200)
    code, _out, err = cca(capsys, IP)
    assert code == 1 and "response larger than 100 bytes" in err


def test_invalid_address_exits_2(project, api, ptr, capsys):
    code, out, err = cca(capsys, "example.com")
    assert code == 2 and out == "" and "invalid IP address 'example.com'" in err
    assert api.requests == []


def test_several_matching_credentials_exit_2(project, api, ptr, capsys):
    creds = dict(CREDENTIALS["credentials"])
    creds["second"] = {"origins": ["https://api.ipapi.is"], "bearer": "second-key"}
    credentials(project, creds)
    code, out, err = cca(capsys, IP)
    assert code == 2 and out == "" and "several credentials" in err
    assert api.requests == []


def test_basic_auth_credential_exits_2(project, api, ptr, capsys):
    credentials(
        project, {"ipapi": {"origins": ["https://api.ipapi.is"], "username": "u", "password": "p"}}
    )
    code, _out, err = cca(capsys, IP)
    assert code == 2 and "must be a bearer token" in err


# --- JSON


def test_json_output(project, api, ptr, capsys):
    code, out, _ = cca(capsys, "--json", IP, "10.0.0.1")
    assert code == 0
    assert json.loads(out) == [
        {
            "ip": IP,
            "bogon": False,
            "reverse": "one.example.net",
            "announced": True,
            "prefix": "1.1.1.0/24",
            "asns": [{"asn": 13335, "holder": "CLOUDFLARENET - Cloudflare, Inc."}],
            "rpki": [{"asn": 13335, "status": "valid"}],
            "abuse_contacts": ["abuse@example.com"],
            "organization": "Example Org",
            "country": "AU",
            "city": "Brisbane",
            "flags": {
                "dc": True,
                "proxy": False,
                "vpn": False,
                "tor": False,
                "mobile": False,
                "abuser": False,
                "crawler": False,
                "anycast": True,
            },
            "errors": {},
        },
        {"ip": "10.0.0.1", "bogon": True},
    ]
