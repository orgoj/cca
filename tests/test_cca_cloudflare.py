"""cca cloudflare: compatibility matrix of doc-5, one test per row.

The real SDK talks to a fake Cloudflare API through an httpx.MockTransport (the module's
TRANSPORT seam); the token comes from a fake `sops` on a PATH that holds only fake tools.
"""

import json
import os
import re
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cca.cli import main
from cca.commands import cloudflare as cf
from cca.output import CcaError

TOKEN = "cf-token-sentinel"
HOSTILE = "hostile-env-sentinel"
API_HOST = "api.example.com"


def hexid(n: int) -> str:
    return f"{n:032x}"


ACCOUNT = {"id": hexid(900), "name": "Example account"}


def zone(n: int, name: str) -> dict:
    return {
        "id": hexid(n),
        "name": name,
        "status": "active",
        "paused": False,
        "plan": {"name": "Free Website"},
        "account": dict(ACCOUNT),
        "name_servers": ["a.ns.example.net", "b.ns.example.net"],
    }


def record(n: int, name: str, rtype: str, content: str, **extra) -> dict:
    return {
        "id": hexid(n),
        "name": name,
        "type": rtype,
        "content": content,
        "ttl": 1,
        "proxied": False,
        **extra,
    }


def rule(n: int, description: str, action: str = "block", **extra) -> dict:
    return {
        "id": hexid(n),
        "description": description,
        "action": action,
        "expression": f'(http.host eq "r{n}.example.com")',
        "enabled": True,
        "version": "1",
        "last_updated": "2026-01-01T00:00:00Z",
        **extra,
    }


class Api:
    """A small in-memory Cloudflare API v4; records every request."""

    def __init__(self):
        self.zones = [zone(1, "example.com"), zone(2, "example.org")]
        self.records: dict[str, list[dict]] = {hexid(1): [], hexid(2): []}
        self.settings: dict[str, list[dict]] = {}
        self.phases: dict[tuple[str, str], dict] = {}  # (zone id, phase) -> ruleset
        self.access: dict[str, list[dict]] = {}
        self.ua: dict[str, list[dict] | int] = {}
        self.bots: dict[str, dict | int] = {}
        self.graphql: list = []  # responses in order (dict or callable(body))
        self.errors: dict[tuple[str, str], tuple[int, dict]] = {}  # (method, path) -> reply
        self.misplace = False  # rule writes land at the end regardless of position
        self.requests: list[httpx.Request] = []
        self.serial = 100

    # -- helpers
    @staticmethod
    def ok(result, info: dict | None = None) -> httpx.Response:
        body = {"success": True, "errors": [], "messages": [], "result": result}
        if info is not None:
            body["result_info"] = info
        return httpx.Response(200, json=body)

    @staticmethod
    def fail(status: int, message: str, code: int = 1000) -> httpx.Response:
        body = {"success": False, "errors": [{"code": code, "message": message}], "messages": []}
        return httpx.Response(status, json=body)

    def page(self, items: list, params) -> httpx.Response:
        page, per_page = int(params.get("page", 1)), int(params.get("per_page", 20))
        total = max(1, -(-len(items) // per_page))
        chunk = items[(page - 1) * per_page : page * per_page]
        info = {
            "page": page,
            "per_page": per_page,
            "count": len(chunk),
            "total_count": len(items),
            "total_pages": total,
        }
        return self.ok(chunk, info)

    def next_id(self) -> str:
        self.serial += 1
        return hexid(self.serial)

    def writes(self) -> list[httpx.Request]:
        return [
            r for r in self.requests if r.method != "GET" and r.url.path != "/client/v4/graphql"
        ]

    # -- routing
    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/client/v4")
        params = request.url.params
        body = json.loads(request.content) if request.content else None
        if (request.method, path) in self.errors:
            status, payload = self.errors[(request.method, path)]
            return httpx.Response(status, json=payload)
        if path == "/zones":
            zones = self.zones
            if "name" in params:
                zones = [z for z in zones if z["name"] == params["name"]]
            return self.page(zones, params)
        if path == "/user/tokens/verify":
            return self.ok({"id": hexid(500), "status": "active", "expires_on": None})
        if path == "/user/tokens":
            policy = {
                "effect": "allow",
                "permission_groups": [{"name": "Zone Read"}],
                "resources": {"com.cloudflare.api.account.zone.*": "*"},
            }
            return self.page([{"id": hexid(500), "policies": [policy]}], params)
        if path == "/graphql":
            reply = self.graphql.pop(0)
            return httpx.Response(200, json=reply(body) if callable(reply) else reply)
        m = re.fullmatch(r"/zones/(\w+)/(.*)", path)
        if not m:
            return self.fail(404, "no route")
        zid, rest = m.groups()
        if rest == "settings":
            return self.ok(self.settings.get(zid, []))
        if rest == "bot_management":
            bots = self.bots.get(zid, {})
            return self.fail(bots, "forbidden") if isinstance(bots, int) else self.ok(bots)
        if rest == "dns_records":
            return self.dns(request.method, zid, None, params, body)
        if rest.startswith("dns_records/"):
            return self.dns(request.method, zid, rest.split("/")[1], params, body)
        if rest == "firewall/access_rules/rules":
            return self.page(self.access.get(zid, []), params)
        if rest == "firewall/ua_rules":
            ua = self.ua.get(zid, [])
            return self.fail(ua, "not available") if isinstance(ua, int) else self.page(ua, params)
        m = re.fullmatch(r"rulesets/phases/(\w+)/entrypoint", rest)
        if m:
            ruleset = self.phases.get((zid, m.group(1)))
            if ruleset is None:
                return self.fail(
                    404, f"could not find entrypoint ruleset in the '{m.group(1)}' phase", 10003
                )
            return self.ok(ruleset)
        if rest == "rulesets" and request.method == "POST":
            ruleset = {"id": self.next_id(), "phase": body["phase"], "rules": []}
            for new in body["rules"]:
                ruleset["rules"].append(dict(new, id=self.next_id(), version="1"))
            self.phases[(zid, body["phase"])] = ruleset
            return self.ok(ruleset)
        m = re.fullmatch(r"rulesets/(\w+)/rules(?:/(\w+))?", rest)
        if m:
            return self.rule_write(request.method, zid, m.group(1), m.group(2), body)
        return self.fail(404, "no route")

    def dns(self, method, zid, rid, params, body) -> httpx.Response:
        records = self.records[zid]
        if method == "GET":
            items = records
            if "name.exact" in params:
                items = [r for r in records if r["name"] == params["name.exact"]]
            return self.page(items, params)
        if method == "POST":
            new = dict(body, id=self.next_id())
            records.append(new)
            return self.ok(new)
        current = next(r for r in records if r["id"] == rid)
        if method == "DELETE":
            records.remove(current)
            return self.ok({"id": rid})
        current.update(body)  # PATCH
        return self.ok(current)

    def rule_write(self, method, zid, ruleset_id, rule_id, body) -> httpx.Response:
        ruleset = next(r for r in self.phases.values() if r["id"] == ruleset_id)
        rules = ruleset["rules"]
        position = body.pop("position", None)
        if method == "POST":
            new = dict(body, id=self.next_id(), version="1")
        else:
            new = next(r for r in rules if r["id"] == rule_id)
            rules.remove(new)
            new.update(body)
        if position is None or self.misplace:
            rules.append(new)
        elif "index" in position:
            rules.insert(position["index"] - 1, new)
        else:
            anchor = [r["id"] for r in rules].index(position.get("before") or position["after"])
            rules.insert(anchor + (0 if "before" in position else 1), new)
        return self.ok(ruleset)


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A project with .cca.toml, sops file, fake sops and the fake API."""
    (tmp_path / ".cca.toml").write_text(
        f'schema_version = 1\n[cloudflare]\napi_base = "https://{API_HOST}/client/v4"\n'
    )
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "cloudflare.secret.yaml").write_text("api_token: ENC[...]\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sops = bindir / "sops"
    sops.write_text(f'#!/bin/sh\necho \'{{"api_token": "{TOKEN}"}}\'\n')
    sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.chdir(tmp_path)
    state = Api()
    monkeypatch.setattr(cf, "TRANSPORT", httpx.MockTransport(state.handle))
    monkeypatch.setattr(cf, "MAX_RETRIES", 0)
    return state


def cca(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(["cloudflare", *argv])
    out, err = capsys.readouterr()
    return code, out, err


Z1 = hexid(1)
WAF = "http_request_firewall_custom"


def waf(api: Api, *rules: dict) -> dict:
    ruleset = {"id": hexid(700), "phase": WAF, "rules": [dict(r) for r in rules]}
    api.phases[(Z1, WAF)] = ruleset
    return ruleset


# ---------------------------------------------------------------- credentials, client


def test_hostile_env_and_missing_secret_fail_closed(api, tmp_path, monkeypatch, capsys):
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_API_KEY",
        "CLOUDFLARE_EMAIL",
        "CLOUDFLARE_API_USER_SERVICE_KEY",
    ):
        monkeypatch.setenv(name, HOSTILE)
    (tmp_path / "secrets" / "cloudflare.secret.yaml").unlink()
    code, out, err = cca(capsys, "zone", "list")
    assert code == 2 and "cloudflare.secret.yaml" in err
    assert api.requests == [] and HOSTILE not in out + err


def test_token_only_from_sops_ambient_sdk_config_ignored(api, monkeypatch, capsys):
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_API_KEY",
        "CLOUDFLARE_EMAIL",
        "CLOUDFLARE_API_USER_SERVICE_KEY",
    ):
        monkeypatch.setenv(name, HOSTILE)
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://evil.example.net/client/v4")
    monkeypatch.setenv("CLOUDFLARE_CUSTOM_HEADERS", f"X-Evil: {HOSTILE}")
    monkeypatch.setenv("CLOUDFLARE_LOG", "debug")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.net:3128")
    code, out, err = cca(capsys, "zone", "list")
    assert code == 0
    request = api.requests[0]
    assert request.url.host == API_HOST
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    sent = " ".join(f"{k}: {v}" for k, v in request.headers.items())
    assert HOSTILE not in sent and "x-auth" not in sent.lower()
    assert request.headers["accept-encoding"] == "identity"
    assert TOKEN not in out + err and HOSTILE not in out + err


def test_client_ignores_environment():
    client = cf.make_client(TOKEN, f"https://{API_HOST}/client/v4")
    assert client._client.trust_env is False and client._client.follow_redirects is False
    client.close()


def test_missing_config_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = cca(capsys, "zone", "list")
    assert code == 2 and ".cca.toml" in err


def test_sdk_error_is_a_clean_exit_1(api, capsys):
    api.errors[("GET", "/zones")] = (
        403,
        {"success": False, "messages": [], "errors": [{"code": 9109, "message": "Unauthorized"}]},
    )
    code, out, err = cca(capsys, "zone", "list")
    assert code == 1 and "HTTP 403: 9109: Unauthorized" in err and "Traceback" not in err


def test_sdk_retries_kept(api, monkeypatch, capsys):
    monkeypatch.setattr(cf, "MAX_RETRIES", 1)
    replies = [Api.fail(503, "busy")]

    def flaky(request):
        return replies.pop() if replies else api.handle(request)

    monkeypatch.setattr(cf, "TRANSPORT", httpx.MockTransport(flaky))
    code, out, _ = cca(capsys, "zone", "list")
    assert code == 0 and "--- 2 zones ---" in out and replies == []


def test_response_size_cap_is_never_retried(api, monkeypatch, capsys):
    monkeypatch.setattr(cf, "MAX_BODY", 100)
    monkeypatch.setattr(cf, "MAX_RETRIES", 2)
    code, _, err = cca(capsys, "zone", "list")
    assert code == 1 and "response larger than 100 bytes" in err
    assert len(api.requests) == 1


def test_total_deadline_covers_slow_responses(api, monkeypatch, capsys):
    monkeypatch.setattr(cf, "DEADLINE", 0.2)
    monkeypatch.setattr(cf, "MAX_RETRIES", 2)  # a deadline is not retried either

    def slow(request):
        time.sleep(1)
        return Api.ok([])

    monkeypatch.setattr(cf, "TRANSPORT", httpx.MockTransport(slow))
    start = time.monotonic()
    code, _, err = cca(capsys, "zone", "list")
    assert code == 1 and "no complete response within 0.2 s" in err
    assert time.monotonic() - start < 1


def test_api_ids_in_request_paths_are_validated(api, capsys):
    api.zones[0]["id"] = "../../user"
    code, _, err = cca(capsys, "zone", "list")
    assert code == 1 and "unexpected zone id" in err


# ---------------------------------------------------------------- usage


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["waf"],
        ["zone", "info", "bad_name!"],
        ["zone", "info", "-x.example.com"],
        [
            "waf",
            "add",
            "example.com",
            "--description",
            "d",
            "--action",
            "skip",
            "--expression",
            "e",
        ],
        ["waf", "move", "example.com", "--rule", "a", "--position", "0"],
        ["events", "example.com", "--limit", "0"],
        ["dns", "ensure-cname", "example.com", "--name", "a b", "--target", "t.example.net"],
    ],
)
def test_usage_errors_exit_2(api, capsys, argv):
    try:
        code = main(["cloudflare", *argv])  # a missing GROUP/COMMAND prints help
    except SystemExit as e:  # argparse
        code = e.code
    assert code == 2
    assert api.requests == []


# ---------------------------------------------------------------- read commands


def test_token_verify_with_policies(api, capsys):
    code, out, _ = cca(capsys, "token", "verify")
    assert code == 0
    assert f"id:      {hexid(500)}" in out and "allow: Zone Read" in out
    assert "  com.cloudflare.api.account.zone.* = *" in out


def test_token_verify_without_list_permission(api, capsys):
    api.errors[("GET", "/user/tokens")] = (403, {"success": False, "errors": [], "messages": []})
    code, out, _ = cca(capsys, "token", "verify")
    assert code == 0 and "unavailable: the token lacks" in out


def test_zone_list_paginates_all_pages(api, capsys):
    api.zones = [zone(i, f"z{i:03}.example.com") for i in range(1, 121)]
    code, out, _ = cca(capsys, "zone", "list")
    assert code == 0 and "--- 120 zones ---" in out
    assert f"z120.example.com\tactive\t{hexid(120)}" in out
    pages = [r.url.params["page"] for r in api.requests]
    assert pages == ["1", "2", "3"]  # total_pages, no extra empty-page request


def test_zone_list_name_filter_and_sort(api, capsys):
    code, out, _ = cca(capsys, "zone", "list", "--name", "ORG")
    assert code == 0
    assert out.splitlines() == [f"example.org\tactive\t{hexid(2)}", "--- 1 zones ---"]


@pytest.mark.parametrize("zones,message", [([], "not found"), (2, "more than one")])
def test_zone_not_found_or_ambiguous_exit_1(api, capsys, zones, message):
    api.zones = [] if zones == [] else [zone(1, "example.com"), zone(3, "example.com")]
    code, _, err = cca(capsys, "zone", "info", "example.com")
    assert code == 1 and message in err


def test_zone_name_compared_case_insensitively(api, capsys):
    code, out, _ = cca(capsys, "zone", "settings", "EXAMPLE.com.")
    assert code == 0 and "=== example.com settings ===" in out


def test_zone_info(api, capsys):
    api.settings[Z1] = [{"id": "ssl", "value": "full"}, {"id": "other", "value": 1}]
    waf(api, rule(1, "a"), rule(2, "b"))
    api.access[Z1] = [{"mode": "block", "configuration": {"target": "ip", "value": "192.0.2.1"}}]
    code, out, _ = cca(capsys, "zone", "info", "example.com")
    assert code == 0
    for line in (
        "plan:        Free Website",
        "nameservers: a.ns.example.net, b.ns.example.net",
        "ssl: full",
        "WAF Custom Rules: 2/5",
        "Rate Limiting Rules: 0/1",
        "Configuration Rules: 0/10",
        "IP Access Rules: 1",
        "User Agent Rules: 0",
    ):
        assert line in out
    assert "other:" not in out  # only audit settings


def test_zone_settings_selected_and_unavailable(api, capsys):
    api.settings[Z1] = [{"id": "ssl", "value": "full"}, {"id": "minify", "value": {"js": "off"}}]
    code, out, _ = cca(
        capsys, "zone", "settings", "example.com", "--setting", "minify", "--setting", "waf"
    )
    assert code == 0
    assert 'minify: {"js": "off"}' in out and "waf: (not available on this plan)" in out


def test_dns_show_domain_flags_missing(api, capsys):
    api.records[Z1] = [
        record(10, "example.com", "A", "192.0.2.1"),
        record(11, "_dmarc.example.com", "TXT", "v=DMARC1; p=none"),
    ]
    code, out, _ = cca(capsys, "dns", "show-domain", "example.com", "example.org")
    assert code == 0
    assert "example.com: example.com A 192.0.2.1 ttl=1 proxied=false" in out
    assert "www: MISSING" in out and "_dmarc: _dmarc.example.com TXT v=DMARC1; p=none" in out
    assert "\n\n=== example.org ===" in out


def test_dns_show_dkim(api, capsys):
    api.records[Z1] = [
        record(10, "s2._domainkey.example.com", "CNAME", "x.example.net."),
        record(11, "s1._domainkey.example.com", "TXT", "v=DKIM1"),
        record(12, "www.example.com", "A", "192.0.2.1"),
    ]
    code, out, _ = cca(capsys, "dns", "show-dkim", "example.com", "example.org")
    lines = out.splitlines()
    assert code == 0 and lines[1].startswith("s1._domainkey") and lines[2].startswith("s2.")
    assert "x.example.net ttl=1" in lines[2]  # trailing dot stripped
    assert "no _domainkey records" in out


def test_dns_dump_zone_stdout_and_file(api, tmp_path, capsys):
    api.records[Z1] = [
        record(11, "b.example.com", "A", "192.0.2.2", comment=None),
        record(10, "a.example.com", "MX", "mx.example.net", priority=10),
    ]
    code, out, _ = cca(capsys, "dns", "dump-zone", "example.com")
    dump = json.loads(out)
    assert code == 0 and dump["schema"] == "cloudflare-dns-dump/1"
    assert list(dump) == ["schema", "exported_at", "zone", "records"]
    assert dump["zone"] == {"id": Z1, "name": "example.com"}
    assert [r["name"] for r in dump["records"]] == ["a.example.com", "b.example.com"]
    assert dump["records"][0]["priority"] == 10 and "comment" not in dump["records"][1]
    assert "id" not in dump["records"][0]
    code, out, _ = cca(capsys, "dns", "dump-zone", "example.com", "-o", "dump.json")
    assert out == "DUMP 2 records -> dump.json\n"
    assert json.loads((tmp_path / "dump.json").read_text())["records"] == dump["records"]


@pytest.mark.parametrize(
    "kind,phase,label",
    [
        ("waf", WAF, "WAF Custom Rules (2/5)"),
        ("ratelimit", "http_ratelimit", "Rate Limiting Rules (2/1)"),
        ("config", "http_config_settings", "Configuration Rules (2/10)"),
    ],
)
def test_rules_list(api, capsys, kind, phase, label):
    api.phases[(Z1, phase)] = {
        "id": hexid(700),
        "rules": [
            rule(1, "first", action_parameters={"products": ["waf"]}),
            rule(2, "second", ratelimit={"period": 10}, enabled=False),
        ],
    }
    code, out, _ = cca(capsys, kind, "list", "example.com")
    assert code == 0 and f"=== example.com - {label} ===" in out
    assert "1. [block] first" in out and "2. [block] [DISABLED] second" in out
    assert f"  id: {hexid(1)}" in out and '  params: {"products": ["waf"]}' in out
    assert '  ratelimit: {"period": 10}' in out


def test_rules_list_missing_entrypoint(api, capsys):
    code, out, _ = cca(capsys, "ratelimit", "list", "example.com")
    assert code == 0 and "(0/1)" in out and "no rules" in out


def test_rules_list_other_read_error_exit_1(api, capsys):
    path = f"/zones/{Z1}/rulesets/phases/{WAF}/entrypoint"
    api.errors[("GET", path)] = (500, {"success": False, "errors": [], "messages": []})
    code, _, err = cca(capsys, "waf", "list", "example.com")
    assert code == 1 and "cannot read rules of phase" in err


def test_api_strings_are_escaped(api, capsys):
    waf(api, rule(1, "evil\x1b[31m‮desc"))
    code, out, _ = cca(capsys, "waf", "list", "example.com")
    assert code == 0 and "\x1b" not in out and "‮" not in out
    assert "evil\\x1b[31m\\u202edesc" in out


def test_json_output_escapes_non_printable(api, capsys):
    api.records[Z1] = [record(10, "a.example.com", "TXT", "x‮y\U000e0001")]
    code, out, _ = cca(capsys, "dns", "dump-zone", "example.com")
    assert "‮" not in out and "\\u202e" in out and "\\udb40\\udc01" in out
    assert json.loads(out)["records"][0]["content"] == "x‮y\U000e0001"


def test_waf_countries(api, tmp_path, capsys):
    waf(
        api,
        rule(1, "geo", expression='(ip.src.country in {"RU" "CN"})'),
        rule(2, "old", action="managed_challenge", expression='ip.geoip.country in {"KP"}'),
    )
    api.phases[(hexid(2), WAF)] = {
        "id": hexid(701),
        "rules": [rule(3, "geo", expression='(ip.src.country in {"RU"})')],
    }
    code, out, _ = cca(capsys, "waf", "countries", "-o", "countries.json")
    assert code == 0
    assert "example.com             3  [block/managed_challenge]  CN KP RU" in out
    assert "CN  1/2  missing: example.org" in out and "RU  2/2" in out
    data = json.loads((tmp_path / "countries.json").read_text())
    assert data["union"] == ["CN", "KP", "RU"] and data["per_zone"]["example.org"] == ["RU"]


def test_access_and_ua_list(api, capsys):
    api.access[Z1] = [
        {
            "mode": "whitelist",
            "notes": "office",
            "configuration": {"target": "ip", "value": "198.51.100.1"},
        },
        {"mode": "block", "configuration": {"target": "country", "value": "AQ"}},
    ]
    api.ua[Z1] = [{"mode": "block", "description": "bad bot", "configuration": {"value": "BadBot"}}]
    code, out, _ = cca(capsys, "access", "list", "example.com")
    lines = out.splitlines()
    assert code == 0 and lines[0].endswith("IP Access Rules (2) ===")
    assert "office" in lines[1] and "AQ" in lines[2]  # sorted by value
    code, out, _ = cca(capsys, "ua", "list", "example.com")
    assert code == 0 and "BadBot  bad bot" in out


def test_ua_list_status_error_is_empty_connection_error_is_fatal(api, monkeypatch, capsys):
    api.ua[Z1] = 400
    code, out, _ = cca(capsys, "ua", "list", "example.com")
    assert code == 0 and "User Agent Rules (0)" in out

    def broken(request):
        if request.url.path.endswith("/ua_rules"):
            raise httpx.ConnectError("refused")
        return api.handle(request)

    monkeypatch.setattr(cf, "TRANSPORT", httpx.MockTransport(broken))
    code, _, err = cca(capsys, "ua", "list", "example.com")
    assert code == 1 and "ConnectError: refused" in err


def test_uam_status(api, capsys):
    api.settings[Z1] = [{"id": "security_level", "value": "under_attack"}]
    api.phases[(Z1, "http_config_settings")] = {
        "id": hexid(702),
        "rules": [
            rule(
                1,
                "uam admin",
                action="set_config",
                action_parameters={"security_level": "under_attack"},
            ),
            rule(2, "other", action="set_config", action_parameters={"ssl": "full"}),
        ],
    }
    code, out, _ = cca(capsys, "uam", "status", "example.com")
    assert code == 0 and "UAM active globally:     YES" in out
    assert "per-URL UAM (Configuration Rules): 1" in out and "uam admin" in out
    assert "other" not in out


def test_bots_status_all_zones_and_raw(api, capsys):
    api.bots[Z1] = {"ai_bots_protection": "block", "fight_mode": True, "extra": 1}
    api.bots[hexid(2)] = 403
    code, out, _ = cca(capsys, "bots", "status")
    assert code == 0 and "ai_bots_protection=block  fight_mode=on" in out
    assert "Example account" in out and "ERROR: HTTP 403" in out and "--- 2 zones ---" in out
    code, out, _ = cca(capsys, "bots", "status", "example.com", "--raw")
    assert '"extra": 1' in out and "--- 1 zones ---" in out


def test_bots_status_connection_error_exit_1(api, monkeypatch, capsys):
    def broken(request):
        if request.url.path.endswith("/bot_management"):
            raise httpx.ConnectError("refused")
        return api.handle(request)

    monkeypatch.setattr(cf, "TRANSPORT", httpx.MockTransport(broken))
    code, _, err = cca(capsys, "bots", "status")
    assert code == 1 and "ConnectError: refused" in err


def events_reply(events: list[dict]) -> dict:
    return {"data": {"viewer": {"zones": [{"firewallEventsAdaptive": events}]}}}


def test_events_summary_and_crawler_warning(api, capsys):
    event = {
        "datetime": "2026-01-01T00:00:00Z",
        "action": "managed_challenge",
        "source": "firewallCustom",
        "clientCountryName": "DE",
        "clientIP": "192.0.2.9",
        "clientRequestPath": "/login",
        "userAgent": "Mozilla/5.0 (compatible; Googlebot/2.1)",
    }
    api.graphql = [events_reply([event, dict(event, userAgent="curl/8")])]
    code, out, _ = cca(capsys, "events", "example.com", "--since", "30m")
    assert code == 0 and "events: 2 (limit 1000" in out
    assert "WARNING: 1 hits on declared search engine crawlers" in out
    assert "       2  managed_challenge" in out and "       2  /login" in out
    sent = json.loads(api.requests[-1].content)
    assert sent["variables"]["limit"] == 1000 and sent["variables"]["zoneTag"] == Z1


def test_events_raw_clamp_and_no_crawlers(api, capsys):
    event = {
        "datetime": "t",
        "action": "block",
        "clientCountryName": "CN",
        "clientIP": "192.0.2.9",
        "clientRequestPath": "/x",
        "userAgent": "curl",
    }
    api.graphql = [events_reply([event]), events_reply([event])]
    code, out, _ = cca(capsys, "events", "example.com", "--since", "2d", "--raw")
    assert code == 0 and "NOTE: --since clamped to" in out and "UA=curl" in out
    code, out, _ = cca(capsys, "events", "example.com")
    assert "no declared crawler among the hits - OK" in out


@pytest.mark.parametrize("since", ["2w", "yesterday", "1e5h"])
def test_events_bad_since_exit_1(api, capsys, since):
    code, _, err = cca(capsys, "events", "example.com", "--since", since)
    assert code == 1 and "invalid --since" in err


def test_parse_since():
    now = datetime(2026, 1, 2, tzinfo=UTC)
    assert cf.parse_since("90m", now) == datetime(2026, 1, 1, 22, 30, tzinfo=UTC)
    assert cf.parse_since("2026-01-01T10:00", now) == datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert cf.parse_since("2026-01-01T10:00+02:00", now) == datetime(2026, 1, 1, 8, tzinfo=UTC)


def test_graphql_errors_exit_1(api, capsys):
    api.graphql = [{"data": None, "errors": [{"message": "zone \x1b not allowed"}]}]
    code, _, err = cca(capsys, "events", "example.com")
    assert code == 1 and "GraphQL error: zone \\x1b not allowed" in err


def test_analytics_hourly_with_breakdowns(api, capsys):
    groups = {
        "data": {
            "viewer": {
                "zones": [
                    {
                        "httpRequestsAdaptiveGroups": [
                            {
                                "dimensions": {"datetimeHour": "2026-01-01T10:00:00Z"},
                                "count": 3000,
                                "sum": {"edgeResponseBytes": 2048, "visits": 10},
                            },
                            {
                                "dimensions": {"datetimeHour": "2026-01-01T11:00:00Z"},
                                "count": 1000,
                                "sum": {"edgeResponseBytes": 0, "visits": 5},
                            },
                        ]
                    }
                ]
            }
        }
    }
    breakdown = {
        "data": {
            "viewer": {
                "zones": [
                    {
                        "httpRequestsAdaptiveGroups": [
                            {
                                "dimensions": {"clientCountryName": "DE"},
                                "count": 4000,
                                "sum": {"visits": 15},
                            }
                        ]
                    }
                ]
            }
        }
    }
    empty = {"data": {"viewer": {"zones": []}}}
    api.graphql = [groups, breakdown, empty, empty]
    code, out, _ = cca(capsys, "analytics", "example.com", "--by", "day")  # default 24h
    assert code == 0 and "requests: 4 000" in out and "visits:   15" in out
    assert "bytes:    2.0 kB" in out and "--- by day ---" in out
    assert "2026-01-01               4 000 req       15 visits" in out
    assert "--- country ---" in out and "    4 000  DE" in out and "--- cache ---" not in out
    assert len(api.graphql) == 0


def test_analytics_daily_for_long_windows(api, capsys):
    daily = {
        "data": {
            "viewer": {
                "zones": [
                    {
                        "httpRequests1dGroups": [
                            {
                                "dimensions": {"date": "2026-01-01"},
                                "uniq": {"uniques": 7},
                                "sum": {
                                    "requests": 100,
                                    "pageViews": 50,
                                    "bytes": 1024,
                                    "threats": 2,
                                    "cachedRequests": 25,
                                },
                            },
                        ]
                    }
                ]
            }
        }
    }
    api.graphql = [daily]
    code, out, _ = cca(capsys, "analytics", "example.com", "--since", "7d", "--no-breakdown")
    assert code == 0 and "source: httpRequests1dGroups" in out
    assert "unique visitors: 7" in out and "threats:  2" in out
    assert "cache  25 %" in out
    query = json.loads(api.requests[-1].content)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", query["variables"]["since"])


# ---------------------------------------------------------------- export, diff


def test_export_default_path_and_diff(api, tmp_path, capsys):
    api.records[Z1] = [record(10, "a.example.com", "A", "192.0.2.1")]
    waf(api, rule(1, "a"))
    code, out, _ = cca(capsys, "export", "example.com")
    path = tmp_path / "tmp" / "cloudflare" / "example.com.json"
    assert code == 0 and f"EXPORT example.com -> {path}" in out
    assert "  waf=1 ratelimit=0 config=0 access=0 ua=0 dns=1" in out
    state = json.loads(path.read_text())
    assert state["schema"] == "cloudflare-zone-export/1" and state["zone"]["status"] == "active"
    code, out, _ = cca(capsys, "diff", "example.com")
    assert code == 0 and out.startswith("OK example.com - no change against")
    api.records[Z1][0]["content"] = "192.0.2.2"
    code, out, _ = cca(capsys, "diff", "example.com")
    assert code == 1 and '-      "content": "192.0.2.1",' in out and "+++ live:example.com" in out


def test_export_dir_from_config_and_cli_paths(api, tmp_path, capsys):
    (tmp_path / ".cca.toml").write_text(
        f'schema_version = 1\n[cloudflare]\napi_base = "https://{API_HOST}/client/v4"\n'
        'export_dir = "state/cf"\n'
    )
    (tmp_path / "sub").mkdir()
    os.chdir(tmp_path / "sub")
    assert cca(capsys, "export", "example.com")[0] == 0
    assert (tmp_path / "state" / "cf" / "example.com.json").exists()
    assert cca(capsys, "export", "example.com", "-o", "mine.json")[0] == 0
    assert (tmp_path / "sub" / "mine.json").exists()
    assert cca(capsys, "diff", "example.com", "-i", "mine.json")[0] == 0


def test_diff_missing_export_exit_1(api, capsys):
    code, _, err = cca(capsys, "diff", "example.com")
    assert code == 1 and "run `cca cloudflare export example.com` first" in err


def test_export_symlink_outside_dir_exit_2(api, tmp_path, capsys):
    (tmp_path / "tmp" / "cloudflare").mkdir(parents=True)
    (tmp_path / "tmp" / "cloudflare" / "example.com.json").symlink_to(tmp_path / "outside.json")
    code, _, err = cca(capsys, "export", "example.com")
    assert code == 2 and "resolves outside" in err and not (tmp_path / "outside.json").exists()


def test_export_symlink_inside_dir_exit_2(api, tmp_path, capsys):
    directory = tmp_path / "tmp" / "cloudflare"
    directory.mkdir(parents=True)
    (directory / "example.org.json").write_text("{}")
    (directory / "example.com.json").symlink_to(directory / "example.org.json")
    code, _, err = cca(capsys, "export", "example.com")
    assert code == 2 and "is a symbolic link" in err
    assert (directory / "example.org.json").read_text() == "{}"


# ---------------------------------------------------------------- generated file names


def test_snapshot_never_aliases_an_export():
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    assert cf.snapshot_name("x", stamp) == "x+20260101t000000z.json"
    assert cf.export_name("x-20260101t000000z") == "x-20260101t000000z.json"
    assert cf.snapshot_name("x", stamp, 2) == "x+20260101t000000z-2.json"


@pytest.mark.parametrize("zone_name", ["con", "aux.example.com", "lpt9.example"])
def test_windows_device_zones_are_hashed(zone_name):
    name = cf.export_name(zone_name)
    assert re.fullmatch(r"zone\+[0-9a-f]{32}\.json", name)
    assert cf.snapshot_name(zone_name, datetime(2026, 1, 1, tzinfo=UTC)).startswith(name[:-5] + "+")


def test_plain_zone_names():
    assert cf.export_name("console.example.com") == "console.example.com.json"
    long_zone = ".".join(["a" * 49] * 3)  # 149 characters
    assert len(cf.snapshot_name(long_zone, datetime(2026, 1, 1, tzinfo=UTC), 999)) <= 200
    with pytest.raises(CcaError):
        cf.export_name("a" * 63 + "." + "b" * 63 + "." + "c" * 30)


# ---------------------------------------------------------------- DNS writes


def test_ensure_cname_plan_changes_nothing(api, capsys):
    code, out, _ = cca(
        capsys,
        "dns",
        "ensure-cname",
        "example.com",
        "--name",
        "Verify",
        "--target",
        "target.example.net.",
    )
    assert code == 0 and out.startswith("MODE: plan\n")
    assert "CREATE verify.example.com -> target.example.net" in out
    assert out.rstrip().endswith("PLAN - nothing changed in Cloudflare (add --apply to write).")
    assert api.writes() == []


def test_ensure_cname_apply_create_ok_update(api, capsys):
    argv = ("dns", "ensure-cname", "example.com", "--name", "@", "--target", "t.example.net")
    assert cca(capsys, *argv, "--apply")[0] == 0
    body = json.loads(api.writes()[0].content)
    assert body == {
        "name": "example.com",
        "type": "CNAME",
        "content": "t.example.net",
        "ttl": 1,
        "proxied": False,
    }
    code, out, _ = cca(capsys, *argv, "--apply")
    assert code == 0 and "OK example.com -> t.example.net" in out and len(api.writes()) == 1
    api.records[Z1][0]["proxied"] = True
    code, out, _ = cca(capsys, *argv, "--apply")
    assert "UPDATE example.com\n  from: example.com CNAME t.example.net ttl=1 proxied=true" in out
    assert api.writes()[-1].method == "PATCH" and api.records[Z1][0]["proxied"] is False


def test_ensure_dkim_conflicts_processed_then_exit_1(api, capsys):
    api.records[Z1] = [
        record(10, "s1._domainkey.example.com", "TXT", "v=DKIM1"),
        record(11, "s3._domainkey.example.com", "CNAME", "a.example.net"),
        record(12, "s3._domainkey.example.com", "CNAME", "b.example.net"),
    ]
    code, out, _ = cca(
        capsys,
        "dns",
        "ensure-dkim",
        "--selector",
        "s1",
        "--selector",
        "s2",
        "--selector",
        "s3",
        "--target-domain",
        "mail.example.net",
        "example.com",
        "example.org",
        "--apply",
    )
    assert code == 1
    assert "CONFLICT s1._domainkey.example.com\n  existing: s1._domainkey.example.com TXT" in out
    assert "CONFLICT s3._domainkey.example.com\n  existing: more than one record" in out
    assert "CREATE s2._domainkey.example.com -> s2._domainkey.mail.example.net" in out
    assert "=== example.org ===" in out
    assert [json.loads(r.content)["name"] for r in api.writes()] == [
        "s2._domainkey.example.com",
        "s1._domainkey.example.org",
        "s2._domainkey.example.org",
        "s3._domainkey.example.org",
    ]


def dump_file(tmp_path: Path, records: list[dict], zone_name: str = "example.com") -> str:
    path = tmp_path / "dump.json"
    path.write_text(
        json.dumps(
            {"schema": "cloudflare-dns-dump/1", "zone": {"name": zone_name}, "records": records}
        )
    )
    return str(path)


def test_restore_zone_plan_and_apply(api, tmp_path, capsys):
    api.records[Z1] = [
        record(10, "a.example.com", "A", "192.0.2.1"),
        record(11, "b.example.com", "A", "192.0.2.2", ttl=300),
        record(12, "extra.example.com", "A", "192.0.2.9"),
    ]
    dump = dump_file(
        tmp_path,
        [
            {
                "name": "a.example.com",
                "type": "A",
                "content": "192.0.2.1",
                "ttl": 1,
                "proxied": False,
            },
            {
                "name": "b.example.com",
                "type": "A",
                "content": "192.0.2.2",
                "ttl": 1,
                "proxied": False,
            },
            {
                "name": "c.example.com",
                "type": "CNAME",
                "content": "x.example.net.",
                "ttl": 1,
                "id": "ignored",
            },
        ],
    )
    code, out, _ = cca(capsys, "dns", "restore-zone", dump)
    assert code == 0 and "MODE: plan" in out and "=== example.com restore (3 records) ===" in out
    assert "CREATE c.example.com CNAME -> x.example.net." in out
    assert "UPDATE b.example.com A\n  from ttl=300 proxied=False\n  to   ttl=1" in out
    assert "--- create=1 update=1 ok=1 delete=0 extras_kept=1 ---" in out
    assert api.writes() == []
    code, out, _ = cca(capsys, "dns", "restore-zone", dump, "--delete-extras", "--apply")
    assert code == 0 and "DELETE extra.example.com A -> 192.0.2.9" in out
    assert [w.method for w in api.writes()] == ["PATCH", "POST", "DELETE"]
    assert "id" not in json.loads(api.writes()[0].content)
    assert sorted(r["name"] for r in api.records[Z1]) == [
        "a.example.com",
        "b.example.com",
        "c.example.com",
    ]


def test_restore_zone_domain_override_and_bad_input(api, tmp_path, capsys):
    dump = dump_file(tmp_path, [], zone_name="other.example")
    code, out, _ = cca(capsys, "dns", "restore-zone", dump, "--domain", "example.org")
    assert code == 0 and "=== example.org restore (0 records) ===" in out
    (tmp_path / "bad.json").write_text('{"schema": "cloudflare-zone-export/1"}')
    code, _, err = cca(capsys, "dns", "restore-zone", "bad.json")
    assert code == 1 and "expected cloudflare-dns-dump/1" in err
    code, _, err = cca(capsys, "dns", "restore-zone", "missing.json")
    assert code == 1 and "not found" in err


# ---------------------------------------------------------------- WAF writes


def snapshots(tmp_path: Path) -> list[str]:
    directory = tmp_path / "tmp" / "cloudflare"
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


ADD = (
    "waf",
    "add",
    "example.com",
    "--description",
    "new",
    "--action",
    "managed_challenge",
    "--expression",
    '(http.request.uri.path eq "/x")',
)


def test_waf_add_plan(api, tmp_path, capsys):
    waf(api, rule(1, "a"))
    code, out, _ = cca(capsys, *ADD)
    assert code == 0
    assert f"account:  Example account ({hexid(900)})" in out
    assert f"ruleset:  {hexid(700)}" in out and "quota:    1/5 -> 2/5" in out
    assert "the rule goes to the END" in out and "  enabled: True" in out
    assert out.rstrip().endswith("(add --apply to write).")
    assert api.writes() == [] and snapshots(tmp_path) == []


def test_waf_add_quota_full_exit_1(api, capsys):
    waf(api, *[rule(i, f"r{i}", enabled=i != 1) for i in range(1, 6)])
    code, _, err = cca(capsys, *ADD)
    assert code == 1 and "5/5 WAF Custom Rules (disabled rules count)" in err


def test_waf_add_apply_snapshot_write_and_read_back(api, tmp_path, capsys):
    waf(api, rule(1, "a"), rule(2, "b"))
    code, out, _ = cca(capsys, *ADD, "--before", hexid(2), "--disabled", "--apply")
    assert code == 0, out
    [snapshot] = snapshots(tmp_path)
    assert re.fullmatch(r"example\.com\+\d{8}t\d{6}z\.json", snapshot)
    assert "pre-write export: " in out and "read-back OK: #2 " in out
    [write] = api.writes()
    body = json.loads(write.content)
    assert write.url.path.endswith(f"/rulesets/{hexid(700)}/rules")
    assert body["position"] == {"before": hexid(2)} and body["enabled"] is False
    rules = api.phases[(Z1, WAF)]["rules"]
    assert [r["description"] for r in rules] == ["a", "new", "b"]


def test_waf_add_creates_missing_entrypoint(api, capsys):
    code, out, _ = cca(capsys, *ADD, "--apply")
    assert code == 0 and "(no zone entrypoint - it will be created)" in out
    assert "created ruleset" in out and "read-back OK: #1" in out
    [write] = api.writes()
    assert write.url.path.endswith(f"/zones/{Z1}/rulesets")
    assert json.loads(write.content)["phase"] == WAF


def test_waf_add_other_read_error_never_creates(api, capsys):
    path = f"/zones/{Z1}/rulesets/phases/{WAF}/entrypoint"
    api.errors[("GET", path)] = (
        404,
        {"success": False, "messages": [], "errors": [{"code": 7003, "message": "no route"}]},
    )
    code, _, err = cca(capsys, *ADD, "--apply")
    assert code == 1 and "cannot read rules of phase" in err and api.writes() == []


def test_waf_snapshot_failure_aborts_before_write(api, tmp_path, capsys):
    waf(api, rule(1, "a"))
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / "cloudflare").write_text("a file, not a directory")
    code, _, err = cca(capsys, *ADD, "--apply")
    assert code == 1 and "pre-write export failed, nothing changed in Cloudflare" in err
    assert api.writes() == []


def test_snapshots_are_never_overwritten(api, tmp_path, monkeypatch, capsys):
    waf(api, rule(1, "a"))
    fixed = datetime(2026, 1, 1, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(cf, "datetime", Clock)
    edit = ("waf", "edit", "example.com", "--rule", hexid(1), "--apply")
    assert cca(capsys, *edit, "--description", "b")[0] == 0
    assert cca(capsys, *edit, "--description", "c")[0] == 0
    assert snapshots(tmp_path) == [
        "example.com+20260101t000000z-2.json",
        "example.com+20260101t000000z.json",
    ]
    first = json.loads((tmp_path / "tmp" / "cloudflare" / snapshots(tmp_path)[1]).read_text())
    assert first["waf_custom_rules"][0]["description"] == "a"


def test_waf_rule_selectors(api, capsys):
    waf(api, rule(1, "same"), rule(2, "same"), rule(3, "unique"))
    base = ("waf", "edit", "example.com", "--description", "x", "--rule")
    code, out, _ = cca(capsys, *base, "3")
    assert code == 0 and f"rule:     #3 {hexid(3)}" in out
    code, out, _ = cca(capsys, *base, "unique")
    assert code == 0 and "#3" in out
    code, out, _ = cca(capsys, *base, hexid(2).upper())
    assert code == 0 and "#2" in out
    code, _, err = cca(capsys, *base, "same")
    assert code == 1 and "matches several rules" in err
    code, _, err = cca(capsys, *base, "4")
    assert code == 1 and "out of range 1-3" in err
    code, _, err = cca(capsys, *base, "3", "--apply")
    assert code == 1 and "cannot be used with --apply" in err and api.writes() == []


def test_waf_edit_keeps_fields_and_verifies(api, tmp_path, capsys):
    waf(
        api,
        rule(
            1,
            "a",
            action="skip",
            action_parameters={"ruleset": "current"},
            logging={"enabled": False},
            ref=None,
        ),
    )
    code, _, err = cca(
        capsys, "waf", "edit", "example.com", "--rule", hexid(1), "--action", "block"
    )
    assert code == 1 and "would invalidate them" in err
    code, out, _ = cca(capsys, "waf", "edit", "example.com", "--rule", hexid(1), "--disable")
    assert code == 0 and "  enabled: True  ->  False" in out and "kept unchanged:" in out
    assert api.writes() == []
    code, out, _ = cca(
        capsys, "waf", "edit", "example.com", "--rule", hexid(1), "--disable", "--apply"
    )
    assert code == 0 and "read-back OK: #1" in out
    body = json.loads(api.writes()[0].content)
    assert body["action_parameters"] == {"ruleset": "current"} and body["enabled"] is False
    assert not {"id", "version", "last_updated", "ref"} & set(body)


def test_waf_edit_nothing_to_change(api, capsys):
    waf(api, rule(1, "a"))
    code, out, _ = cca(capsys, "waf", "edit", "example.com", "--rule", "a", "--enable", "--apply")
    assert code == 0 and "Nothing to change." in out and api.writes() == []


def test_waf_edit_without_ruleset_exit_1(api, capsys):
    code, _, err = cca(capsys, "waf", "edit", "example.com", "--rule", "a")
    assert code == 1 and "nothing to edit" in err


def test_waf_move(api, capsys):
    waf(api, rule(1, "a"), rule(2, "b"), rule(3, "c"))
    code, _, err = cca(capsys, "waf", "move", "example.com", "--rule", "b", "--after", "b")
    assert code == 1 and "the anchor is the rule being moved" in err
    code, out, _ = cca(capsys, "waf", "move", "example.com", "--rule", "c", "--position", "1")
    assert code == 0 and "  3. [block] c <-" in out and api.writes() == []
    code, out, _ = cca(
        capsys, "waf", "move", "example.com", "--rule", hexid(3), "--after", hexid(1), "--apply"
    )
    assert code == 0 and "read-back OK: #2" in out
    assert json.loads(api.writes()[0].content)["position"] == {"after": hexid(1)}
    assert [r["description"] for r in api.phases[(Z1, WAF)]["rules"]] == ["a", "c", "b"]


def test_waf_read_back_mismatch_exit_1(api, capsys):
    waf(api, rule(1, "a"), rule(2, "b"))
    api.misplace = True
    code, _, err = cca(
        capsys, "waf", "move", "example.com", "--rule", hexid(2), "--before", hexid(1), "--apply"
    )
    assert code == 1 and "read-back does not match the write" in err
    assert f"expected right before {hexid(1)} (#1), is #2" in err


def test_waf_write_rejected_exit_1(api, capsys):
    waf(api, rule(1, "a"))
    api.errors[("POST", f"/zones/{Z1}/rulesets/{hexid(700)}/rules")] = (
        400,
        {"success": False, "messages": [], "errors": [{"code": 20021, "message": "bad expr"}]},
    )
    code, _, err = cca(capsys, *ADD, "--apply")
    assert code == 1 and "Cloudflare rejected the write: HTTP 400: 20021: bad expr" in err
