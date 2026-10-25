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


RANGE = {
    "startAddress": "1.1.1.0",
    "endAddress": "1.1.1.255",
    "name": "APNIC-LABS",
    "handle": "1.1.1.0 - 1.1.1.255",
    "type": "ASSIGNED PORTABLE",
}
RIPE_PATH = "/rdap/ripe/ip/"  # the RDAP table points both RIRs at the local server
ARIN_PATH = "/rdap/arin/registry/ip/"


class Api:
    """Routes by path to a dict, a (status, body[, location]) tuple or "<slow>"; default 404."""

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
            RIPE_PATH + IP: RANGE,
        }
        self.requests: list[tuple[str, str, dict, bytes]] = []
        self.accept: dict[str, str | None] = {}  # path -> Accept header

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
        if isinstance(route, list):  # ["<sleep>", seconds, route]: answer late
            time.sleep(route[1])
            return route[2] if isinstance(route[2], tuple) else (200, json.dumps(route[2]))
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
            state.accept[url.path] = self.headers.get("Accept")
            status, body, *location = state.respond(
                method, url.path, query, self.rfile.read(length)
            )
            self.send_response(status)
            if location:
                if location[0] is not None:
                    self.send_header("Location", location[0])
            elif status == 302:
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
    monkeypatch.setattr(asn, "RDAP", [(base, RIPE_PATH, "ripe"), (base, ARIN_PATH, "arin")])
    state.base = base
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
    assert (
        out
        == "1.1.1.1|AS13335|AU|dc,anycast|rpki:valid|Example Org|one.example.net|net:1.1.1.0/24\n"
    )
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
    assert (
        out == "1.1.1.1|AS13335|Australia|?|rpki:valid|Keyless Org|one.example.net|net:1.1.1.0/24\n"
    )
    assert err.count("keyless") == 1
    method, _path, query, body = next(r for r in api.requests if r[1] == "/ipapi/")
    assert (method, query, body) == ("GET", {"q": IP}, b"")


def test_keyless_note_once_for_several_addresses(project, api, ptr, capsys):
    credentials(project, {"other": CREDENTIALS["credentials"]["other"]})
    api.routes[RIPE_PATH + "8.8.8.8"] = RANGE | {
        "startAddress": "8.8.8.0",
        "endAddress": "8.8.8.255",
    }
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
    assert out == "1.1.1.1|AS-|AU|dc,anycast|rpki:-|Example Org|one.example.net|net:1.1.1.0/24\n"
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
    assert out.endswith("|Example Org|-|net:1.1.1.0/24\n")


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
    assert (
        out == "1.1.1.1|AS13335|?|?|rpki:valid|CLOUDFLARENET - Cloudflare, Inc.|?|net:1.1.1.0/24\n"
    )
    assert "1.1.1.1: ipapi: HTTP 429: quota (ipapi.is daily quota used up)" in err
    assert "1.1.1.1: reverse:" in err


def test_ripestat_failure_skips_rpki(project, api, ptr, capsys):
    api.routes["/data/prefix-overview/data.json"] = (500, "oops")
    code, out, err = cca(capsys, IP)
    assert code == 1
    assert out == "1.1.1.1|?|AU|dc,anycast|rpki:?|Example Org|one.example.net|net:1.1.1.0/24\n"
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
            "registry": {
                "range": "1.1.1.0 - 1.1.1.255",
                "cidrs": ["1.1.1.0/24"],
                "name": "APNIC-LABS",
                "handle": "1.1.1.0 - 1.1.1.255",
                "type": "ASSIGNED PORTABLE",
                "rir": "ripe",
            },
            "errors": {},
            "skipped": {},
        },
        {"ip": "10.0.0.1", "bogon": True},
    ]


KEYLESS_IPAPI = {  # the keyless answer: flat country name, no type flags used
    "ip": IP,
    "company": {"name": "Example Org", "type": "hosting"},
    "country": "Australia",
    "city": "Brisbane",
}
KEYLESS_ELEMENT = {  # the JSON contract of one keyless public address (references/asn.md)
    "ip": IP,
    "bogon": False,
    "reverse": "one.example.net",
    "announced": True,
    "prefix": "1.1.1.0/24",
    "asns": [{"asn": 13335, "holder": "CLOUDFLARENET - Cloudflare, Inc."}],
    "rpki": [{"asn": 13335, "status": "valid"}],
    "abuse_contacts": ["abuse@example.com"],
    "organization": "Example Org",
    "country": "Australia",
    "city": "Brisbane",
    "flags": None,
    "registry": {
        "range": "1.1.1.0 - 1.1.1.255",
        "cidrs": ["1.1.1.0/24"],
        "name": "APNIC-LABS",
        "handle": "1.1.1.0 - 1.1.1.255",
        "type": "ASSIGNED PORTABLE",
        "rir": "ripe",
    },
    "errors": {},
    "skipped": {},
}


def test_json_contract_keyless_quota_and_failed_source(tmp_path, monkeypatch, api, ptr, capsys):
    """The four element shapes documented in references/asn.md, key for key."""
    monkeypatch.chdir(tmp_path)  # no project: keyless
    api.routes["/ipapi/"] = KEYLESS_IPAPI
    code, out, _ = cca(capsys, "--json", IP, "192.168.1.1")
    assert code == 0
    assert json.loads(out) == [KEYLESS_ELEMENT, {"ip": "192.168.1.1", "bogon": True}]

    api.routes["/ipapi/"] = (429, json.dumps({"error": "quota"}))
    code, out, _ = cca(capsys, "--json", IP)
    assert code == 0  # a skipped keyless ipapi.is is not a failure
    quota = dict(KEYLESS_ELEMENT, organization=None, country=None, city=None)
    quota["skipped"] = {"ipapi": "keyless daily quota used up"}
    assert json.loads(out) == [quota]

    api.routes["/ipapi/"] = KEYLESS_IPAPI
    api.routes[RIPE_PATH + IP] = (503, "{}")
    code, out, err = cca(capsys, "--json", IP)
    assert code == 1 and "cca: 1.1.1.1: rdap: HTTP 503" in err
    failed = dict(KEYLESS_ELEMENT, registry=None, errors={"rdap": "HTTP 503"})
    assert json.loads(out) == [failed]


# --- RDAP registry range


def registry(capsys) -> tuple[int, dict, str]:
    code, out, err = cca(capsys, "--json", IP)
    (result,) = json.loads(out)
    return code, result, err


def test_rdap_redirect_to_an_allowed_rir_is_followed(project, api, ptr, capsys):
    api.routes[RIPE_PATH + IP] = (301, "", api.base + ARIN_PATH + IP)
    api.routes[ARIN_PATH + IP] = RANGE
    code, result, _err = registry(capsys)
    assert code == 0 and result["registry"]["rir"] == "arin"
    assert [p for _m, p, _q, _b in api.requests if p.startswith("/rdap/")] == [
        RIPE_PATH + IP,
        ARIN_PATH + IP,
    ]


def test_rdap_ipv6_path_in_another_spelling(project, api, ptr, capsys):
    ip6 = "2606:4700:4700::1111"  # global; the local server answers, nothing leaves the host
    six = {
        "startAddress": "2606:4700:4700::",
        "endAddress": "2606:4700:4700:ffff:ffff:ffff:ffff:ffff",
    }
    spelled = "2606:4700:4700:0:0:0:0:1111".upper()
    api.routes[RIPE_PATH + ip6] = (303, "", api.base + ARIN_PATH + spelled)
    api.routes[ARIN_PATH + ip6] = six
    code, out, _err = cca(capsys, ip6)
    assert out.rstrip().endswith("|net:2606:4700:4700::/48")
    assert ARIN_PATH + ip6 in [p for _m, p, _q, _b in api.requests]  # rebuilt canonical


@pytest.mark.parametrize(
    "location",
    [
        "https://rdap.example.com/ip/1.1.1.1",  # other host
        "{base}/rdap/other/ip/1.1.1.1",  # wrong path prefix
        "{base}" + ARIN_PATH + "8.8.8.8",  # other address
        "{base}" + ARIN_PATH + "1.1.1.1?x=1",  # query
        "{base}" + ARIN_PATH + "1.1.1.1#f",  # fragment
        "{userinfo}" + ARIN_PATH + "1.1.1.1",  # userinfo
        "{otherport}" + ARIN_PATH + "1.1.1.1",  # other port
        "{https}" + ARIN_PATH + "1.1.1.1",  # other scheme
        ARIN_PATH + "1.1.1.1",  # relative
    ],
)
def test_rdap_redirect_refused(project, api, ptr, capsys, location):
    scheme, hostport = api.base.split("://")
    host, port = hostport.split(":")
    target = location.format(
        base=api.base,
        userinfo=f"{scheme}://u:p@{hostport}",
        otherport=f"{scheme}://{host}:{int(port) + 1}",
        https=f"https://{hostport}",
    )
    api.routes[RIPE_PATH + IP] = (301, "", target)
    api.routes[ARIN_PATH + IP] = RANGE
    code, result, err = registry(capsys)
    assert code == 1 and result["registry"] is None
    assert "rdap: redirect to '" in err and "not allowed" in err
    assert ARIN_PATH + IP not in [p for _m, p, _q, _b in api.requests]


def test_rdap_redirect_without_location(project, api, ptr, capsys):
    api.routes[RIPE_PATH + IP] = (307, "", None)
    code, _result, err = registry(capsys)
    assert code == 1 and "rdap: redirect without location" in err


def test_rdap_too_many_redirects(project, api, ptr, capsys):
    api.routes[RIPE_PATH + IP] = (301, "", api.base + ARIN_PATH + IP)
    api.routes[ARIN_PATH + IP] = (301, "", api.base + RIPE_PATH + IP)
    code, _result, err = registry(capsys)
    assert code == 1 and "rdap: too many redirects" in err
    assert len([p for _m, p, _q, _b in api.requests if p.startswith("/rdap/")]) == 3


def test_rdap_one_deadline_for_the_chain(project, api, ptr, capsys, monkeypatch):
    monkeypatch.setattr(asn, "TIMEOUT", 2)
    monkeypatch.setattr(asn, "SLACK", 0.5)  # 2.5 s for the whole chain
    # each hop alone fits 2.5 s, both together do not: a per-hop deadline would succeed
    api.routes[RIPE_PATH + IP] = ["<sleep>", 1.5, (301, "", api.base + ARIN_PATH + IP)]
    api.routes[ARIN_PATH + IP] = ["<sleep>", 1.5, RANGE]
    code, result, err = registry(capsys)
    assert code == 1 and result["registry"] is None and "rdap: timed out" in err


@pytest.mark.parametrize(
    "body",
    [
        {"name": "no range"},
        {"startAddress": "1.1.1.0", "endAddress": "garbage"},
        {"startAddress": 16843008, "endAddress": 16843263},
        {"startAddress": "2001:db8::", "endAddress": "2001:db8::ff"},
        {"startAddress": "1.1.2.0", "endAddress": "1.1.2.255"},
    ],
)
def test_rdap_invalid_range(project, api, ptr, capsys, body):
    api.routes[RIPE_PATH + IP] = body
    code, result, err = registry(capsys)
    assert code == 1 and result["registry"] is None and "rdap: invalid range" in err
    _code, out, _err = cca(capsys, IP)
    assert out.rstrip().endswith("|net:?")


def test_rdap_range_summarized_into_cidrs(project, api, ptr, capsys):
    api.routes[RIPE_PATH + IP] = {"startAddress": "1.1.0.0", "endAddress": "1.1.2.255"}
    code, result, _err = registry(capsys)
    assert code == 0 and result["registry"]["cidrs"] == ["1.1.0.0/23", "1.1.2.0/24"]
    _code, out, _err = cca(capsys, IP)
    assert out.rstrip().endswith("|net:1.1.0.0/23+1.1.2.0/24")


def test_rdap_asks_for_rdap_json(project, api, ptr, capsys):
    cca(capsys, IP)
    assert api.accept[RIPE_PATH + IP] == "application/rdap+json, application/json;q=0.9"
    assert api.accept["/data/prefix-overview/data.json"] == "application/json"


def test_rdap_http_error(project, api, ptr, capsys):
    api.routes[RIPE_PATH + IP] = (404, json.dumps({"title": "not found"}))
    code, result, err = registry(capsys)
    assert code == 1 and "rdap: HTTP 404" in err


# --- keyless ipapi.is quota


def test_keyless_quota_degrades_without_failing(tmp_path, monkeypatch, api, ptr, capsys):
    monkeypatch.chdir(tmp_path)  # no project: keyless
    api.routes["/ipapi/"] = (429, json.dumps({"error": "quota"}))
    others = ("8.8.8.8", "9.9.9.9")
    for other in others:
        api.routes[RIPE_PATH + other] = RANGE | {
            "startAddress": "0.0.0.1",
            "endAddress": "223.255.255.255",
        }
    code, out, err = cca(capsys, IP, *others)
    assert code == 0
    assert err.count("ipapi.is keyless daily quota used up: country and city unavailable") == 1
    assert "1.1.1.1: ipapi" not in err
    assert [p for _m, p, _q, _b in api.requests].count("/ipapi/") == 1
    first = out.splitlines()[0]
    assert first == (
        "1.1.1.1|AS13335|?|?|rpki:valid|CLOUDFLARENET - Cloudflare, Inc.|one.example.net"
        "|net:1.1.1.0/24"
    )
    code, out, _err = cca(capsys, "--json", IP, *others)
    assert [r["skipped"] for r in json.loads(out)] == [{"ipapi": "keyless daily quota used up"}] * 3
    assert all(r["errors"] == {} for r in json.loads(out))


def test_keyless_quota_without_holder_prints_dash(tmp_path, monkeypatch, api, ptr, capsys):
    monkeypatch.chdir(tmp_path)
    api.routes["/ipapi/"] = (429, "{}")
    api.routes["/data/prefix-overview/data.json"] = ripe(
        {"announced": False, "resource": IP, "asns": []}
    )
    code, out, _err = cca(capsys, IP)
    assert code == 0
    assert out == "1.1.1.1|AS-|?|?|rpki:-|-|one.example.net|net:1.1.1.0/24\n"


def test_keyed_429_still_fails(project, api, ptr, capsys):
    api.routes["/ipapi/"] = (429, json.dumps({"error": "quota"}))
    code, out, err = cca(capsys, IP)
    assert code == 1 and "1.1.1.1: ipapi: HTTP 429" in err
    assert "keyless daily quota" not in err


def test_keyless_other_error_still_fails(tmp_path, monkeypatch, api, ptr, capsys):
    monkeypatch.chdir(tmp_path)
    api.routes["/ipapi/"] = (500, "{}")
    code, _out, err = cca(capsys, IP)
    assert code == 1 and "1.1.1.1: ipapi: HTTP 500" in err
