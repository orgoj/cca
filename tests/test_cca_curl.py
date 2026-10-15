"""cca curl: option passthrough, URL and credential checks, secrets out of argv and output.

A fake `curl` (a /bin/sh script on a PATH that holds only fake tools) answers
`--help all` from a fixture of the real table, logs argv and the config it reads on
stdin, and reflects that config to stdout, stderr and an optional file, so every
output path carries the secrets unless cca redacts them.
"""

import base64
import io
import json
import shutil
import stat
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

from cca.cli import main
from cca.commands import curl as cc

FIXTURES = Path(__file__).parent / "fixtures"
REAL_CURL = shutil.which("curl")  # before any test replaces PATH
BEARER = "tok-sentinel/1+2"
USER = "admin"
PASSWORD = 'pa"ss\\word-sentinel'
BASIC = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
SECRETS = (BEARER, quote(BEARER, safe=""), quote_plus(BEARER), PASSWORD, BASIC)
CREDENTIALS = {
    "credentials": {
        "example_api": {"origins": ["https://api.example.com"], "bearer": BEARER},
        "example_panel": {
            "origins": ["https://panel.example.com:8443/"],
            "username": USER,
            "password": PASSWORD,
            "csrf": True,
        },
        "shared_a": {"origins": ["https://shared.example.com"], "bearer": "shared-a-token"},
        "shared_b": {"origins": ["https://shared.example.com"], "bearer": "shared-b-token"},
    }
}
FAKE_CURL = """#!/bin/sh
if [ "$1" = "--help" ]; then cat "$FAKE_DIR/help.txt"; exit 0; fi
printf '%s\\n' "${SSLKEYLOGFILE-unset}" > "$FAKE_DIR/keylog"
printf '=== call\\n' >> "$FAKE_DIR/argv"
printf '%s\\n' "$@" >> "$FAKE_DIR/argv"
config=$(cat)
printf '=== call\\n%s\\n' "$config" >> "$FAKE_DIR/config"
if [ "$2" = "-s" ]; then
    printf '<html><meta name="csrf-token" content="csrf-sentinel"></html>\\n'
    exit 0
fi
printf 'OUT %s\\n' "$config"
printf 'ERR %s\\n' "$config" >&2
if [ -n "$FAKE_WRITE" ]; then printf '%s\\n' "$config" > "$FAKE_WRITE"; fi
exit "${FAKE_EXIT:-0}"
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with .cca.toml, a sops file, fake sops and fake curl; returns the log dir."""
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "curl.secret.yaml").write_text("credentials: ENC[...]\n")
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "plain.json").write_text(json.dumps(CREDENTIALS))
    shutil.copy(FIXTURES / "curl-help-all.txt", fake / "help.txt")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "cat").symlink_to(shutil.which("cat"))
    tool(bindir / "sops", f"#!/bin/sh\ncat {fake / 'plain.json'}\n")
    tool(bindir / "curl", FAKE_CURL)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("FAKE_DIR", str(fake))
    monkeypatch.delenv("FAKE_WRITE", raising=False)
    monkeypatch.delenv("FAKE_EXIT", raising=False)
    monkeypatch.chdir(tmp_path)
    return fake


def tool(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def cca(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(["curl", *argv])
    out, err = capsys.readouterr()
    for secret in SECRETS:  # never in any cca output, whatever the test checks
        assert secret not in out and secret not in err
    return code, out, err


def calls(fake: Path, name: str) -> list[list[str]]:
    """Logged argv or config of each curl call (help calls are not logged)."""
    path = fake / name
    if not path.exists():
        return []
    chunks = path.read_text().split("=== call\n")[1:]
    return [chunk.splitlines() for chunk in chunks]


def options() -> cc.Options:
    return cc.Options((FIXTURES / "curl-help-all.txt").read_text())


# ---------------------------------------------------------------- option table, parsing


def test_option_table_from_curl_help():
    opts = options()
    assert opts.lookup("data") is True
    assert opts.lookup("silent") is False
    assert opts.lookup("no-silent") is False  # --no-NAME of a boolean
    assert opts.lookup("no-data") is None  # not for options with a value
    assert opts.lookup("sil") is None  # no abbreviations
    assert opts.short["X"] == "request" and opts.short["#"] == "progress-bar"


def test_option_table_unreadable():
    with pytest.raises(cc.CcaError, match="option table"):
        cc.Options("curl 7.1 usage: curl [options] url\n")


def test_parse_clusters_values_and_end_of_options():
    req = cc.parse(
        ["-sSfo", "out.json", "-XPOST", "-H", "A: b", "-d", "-x", "--no-silent", "--",
         "https://api.example.com/x"],
        options(),
    )  # fmt: skip
    assert req.url == "https://api.example.com/x"
    assert req.items == [
        ("silent", None), ("show-error", None), ("fail", None), ("output", "out.json"),
        ("request", "POST"), ("header", "A: b"), ("data", "-x"), ("no-silent", None),
    ]  # fmt: skip


def test_parse_url_option_and_cred_id():
    req = cc.parse(["--cred-id", "example_api", "--url", "https://api.example.com/"], options())
    assert (req.url, req.cred_id, req.items) == ("https://api.example.com/", "example_api", [])


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--bogus", "https://api.example.com/"], "unknown curl option '--bogus'"),
        (["--request=POST", "https://api.example.com/"], "unknown curl option"),
        (["-sW", "https://api.example.com/"], "unknown curl option '-W'"),
        (["https://api.example.com/", "-H"], "--header needs a value"),
        (["-s"], "no URL given"),
    ],
)
def test_parse_usage_errors(argv, message):
    with pytest.raises(cc.CcaError, match=message):
        cc.parse(argv, options())


@pytest.mark.parametrize(
    "argv",
    [
        ["-L"], ["-sL"], ["--location"], ["--location-trusted"], ["-K", "f.cfg"],
        ["--config", "f.cfg"], ["--expand-config", "{{f}}"],
        ["--expand-url", "https://api.example.com/{{p}}"],
    ],
)  # fmt: skip
def test_rejected_options(project, capsys, argv):
    code, _out, err = cca(capsys, *argv, "https://api.example.com/")
    assert code == 2 and "is not allowed" in err
    assert calls(project, "argv") == []


@pytest.mark.parametrize(
    "argv",
    [
        ["https://api.example.com/a", "https://api.example.com/b"],
        ["https://api.example.com/a", "--url", "https://api.example.com/b"],
        ["--", "https://api.example.com/a", "https://evil.example.net/"],
        ["-sS", "https://api.example.com/a", "evil.example.net"],
    ],
)
def test_second_url_rejected(project, capsys, argv):
    code, _out, err = cca(capsys, *argv)
    assert code == 2 and "only one URL" in err
    assert calls(project, "argv") == []


# ---------------------------------------------------------------- URL and credential


@pytest.mark.parametrize(
    "url, message",
    [
        ("http://api.example.com/", "scheme must be https"),
        ("api.example.com/", "scheme must be https"),
        ("https://user@api.example.com/", "userinfo"),
        ("https://api.example.com\\@evil.example.net/", "backslash"),
        ("-", "scheme must be https"),
    ],
)
def test_invalid_url(project, capsys, url, message):
    code, _out, err = cca(capsys, url)
    assert code == 2 and message in err
    assert calls(project, "argv") == []


def test_credential_by_normalized_origin(project, capsys):
    code, _out, _err = cca(capsys, "https://API.Example.com.:443/v1")
    assert code == 0
    assert calls(project, "config")[0][:3] == [
        'url = "https://API.Example.com.:443/v1"',
        "globoff",
        f'header = "Authorization: Bearer {BEARER}"',
    ]


def test_no_credential_for_origin(project, capsys):
    code, _out, err = cca(capsys, "https://api.example.com:8443/")
    assert code == 2
    assert "no credential allows the origin" in err and "example_api, example_panel" in err


def test_several_credentials_need_cred_id(project, capsys):
    code, _out, err = cca(capsys, "https://shared.example.com/")
    assert code == 2 and "use --cred-id (shared_a, shared_b)" in err
    assert cca(capsys, "--cred-id", "shared_b", "https://shared.example.com/")[0] == 0
    assert 'header = "Authorization: Bearer shared-b-token"' in calls(project, "config")[0]


def test_cred_id_must_allow_origin(project, capsys):
    code, _out, err = cca(capsys, "--cred-id", "example_panel", "https://api.example.com/")
    assert code == 2 and "does not allow the origin" in err
    code, _out, err = cca(capsys, "--cred-id", "a) | .x", "https://api.example.com/")
    assert code == 2 and "unknown credential 'a) | .x'" in err


def test_options_are_checked_before_secrets_are_read(project, capsys):
    (project / "plain.json").unlink()  # sops would fail
    assert cca(capsys, "-L", "https://api.example.com/")[0] == 2


# ---------------------------------------------------------------- secrets out of argv


def test_token_and_auth_only_in_config(project, capsys):
    code, _out, _err = cca(
        capsys,
        "-s", "-H", "X-Key: {TOKEN}", "-d", "a=1", "--data-urlencode", "t={TOKEN}",
        "https://api.example.com/v1/{TOKEN}/list",
    )  # fmt: skip
    assert code == 0
    (argv,) = calls(project, "argv")
    assert argv == ["-q", "--config", "-", "--silent", "--data", "a=1"]
    (config,) = calls(project, "config")
    assert config == [
        f'url = "https://api.example.com/v1/{BEARER}/list"',
        "globoff",
        f'header = "Authorization: Bearer {BEARER}"',
        f'header = "X-Key: {BEARER}"',
        f'data-urlencode = "t={BEARER}"',
    ]


def test_basic_auth_escaped_in_config(project, capsys):
    assert cca(capsys, "https://panel.example.com:8443/")[0] == 0
    config = calls(project, "config")[1]  # [0] is the CSRF fetch
    assert 'user = "admin:pa\\"ss\\\\word-sentinel"' in config


def test_token_needs_bearer_credential(project, capsys):
    code, _out, err = cca(capsys, "https://panel.example.com:8443/{TOKEN}")
    assert code == 2 and "needs a bearer credential ('example_panel'" in err
    assert calls(project, "argv") == []


def test_control_character_in_config_value(project, capsys):
    code, _out, err = cca(capsys, "-H", "X-Key: {TOKEN}\r\nX-Evil: 1", "https://api.example.com/")
    assert code == 2 and "control character" in err
    assert calls(project, "argv") == []


def test_csrf_token_fetched_with_same_credential(project, capsys):
    assert cca(capsys, "-X", "POST", "https://panel.example.com:8443/form")[0] == 0
    fetch, request = calls(project, "argv")
    assert fetch == ["-q", "-s", "--config", "-"]
    assert request == ["-q", "--config", "-", "--request", "POST"]
    fetch_config, config = calls(project, "config")
    assert fetch_config == config[:3]
    assert config[3] == 'header = "X-CSRF-Token: csrf-sentinel"'


def test_csrf_patterns():
    pages = {
        '<meta name="csrf-token" content="a1">': "a1",
        "<input name='_token' type=hidden value='b2'>": "b2",
        '<meta content="c3" name="csrf-token">': "c3",
        "<p>no token</p>": None,
    }
    for page, token in pages.items():
        found = next((m.group(1) for p in cc.CSRF_PATTERNS if (m := p.search(page))), None)
        assert found == token


# ---------------------------------------------------------------- redaction


def test_reflected_secrets_redacted_from_stdout_and_stderr(project, capsys):
    code, out, err = cca(capsys, "https://api.example.com/v1/{TOKEN}")
    assert code == 0
    assert 'OUT url = "https://api.example.com/v1/[REDACTED]"' in out
    assert 'ERR url = "https://api.example.com/v1/[REDACTED]"' in err
    assert "Authorization: Bearer [REDACTED]" in out


def test_basic_and_csrf_redacted(project, capsys):
    code, out, _err = cca(capsys, "https://panel.example.com:8443/")
    assert code == 0
    assert 'user = "admin:pa\\"ss\\\\word-sentinel"' not in out
    assert "csrf-sentinel" not in out and "X-CSRF-Token: [REDACTED]" in out


class ClosedPipe(io.BytesIO):
    def write(self, data):
        raise BrokenPipeError


class Proc:
    killed = False

    def kill(self):
        self.killed = True


def test_pump_stops_curl_when_reader_is_gone():
    """`cca curl ... | head`: curl is killed and its pipe drained instead of blocking."""
    proc, source = Proc(), io.BytesIO(b"x" * 300_000)
    cc._pump(source, ClosedPipe(), cc.Redactor([b"secret"]), proc)
    assert proc.killed and source.read() == b""


def test_redactor_across_chunk_boundaries():
    secrets = [b"secret", b"secret-longer", b"%2Fx"]
    data = b"a secret b secret-longer c secre"
    expected = b"a [REDACTED] b [REDACTED] c secre"
    for size in (1, 2, 5, 7, len(data)):
        r = cc.Redactor(secrets)
        out = b"".join(r.feed(data[i : i + size]) for i in range(0, len(data), size))
        assert out + r.feed(b"", final=True) == expected


def test_secret_forms():
    cred = cc.secrets.Credential("x", (), bearer="a/b c")
    assert set(cc.secret_values(cred)) == {b"a/b c", b"a%2Fb%20c", b"a/b%20c", b"a%2Fb+c"}


@pytest.mark.parametrize(
    "argv, target",
    [
        (["--trace", "t.txt"], "t.txt"),
        (["--trace-ascii", "t.txt"], "t.txt"),
        (["--libcurl", "c.c"], "c.c"),
        (["--stderr", "e.txt"], "e.txt"),
        (["-sD", "h.txt"], "h.txt"),
        (["-w", "%{http_code}%output{>>w.txt}%{url}"], "w.txt"),
        (["--output-dir", "dl", "-D", "h.txt"], "dl/h.txt"),
    ],
)
def test_files_with_request_data_redacted(project, capsys, monkeypatch, argv, target):
    Path("dl").mkdir()
    monkeypatch.setenv("FAKE_WRITE", target)
    assert cca(capsys, *argv, "https://api.example.com/{TOKEN}")[0] == 0
    text = Path(target).read_text()
    assert "Bearer [REDACTED]" in text and BEARER not in text


def test_trace_file_through_symlink_redacted(project, capsys, monkeypatch):
    Path("real.txt").write_text("")
    Path("link.txt").symlink_to("real.txt")
    monkeypatch.setenv("FAKE_WRITE", "link.txt")
    assert cca(capsys, "--trace", "link.txt", "https://api.example.com/")[0] == 0
    assert Path("link.txt").is_symlink() and BEARER not in Path("real.txt").read_text()


def test_output_file_unchanged(project, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_WRITE", "out.json")
    assert cca(capsys, "-o", "out.json", "https://api.example.com/")[0] == 0
    assert BEARER in Path("out.json").read_text()


# ---------------------------------------------------------------- process


def test_exit_code_passes_through(project, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_EXIT", "22")
    assert cca(capsys, "-f", "https://api.example.com/")[0] == 22


def test_tls_key_log_not_passed_to_curl(project, capsys, monkeypatch):
    monkeypatch.setenv("SSLKEYLOGFILE", "/tmp/keys.log")
    assert cca(capsys, "https://api.example.com/")[0] == 0
    assert (project / "keylog").read_text() == "unset\n"


def test_help_needs_no_config_or_curl(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    code, out, _err = cca(capsys, "--help")
    assert code == 0 and "usage: cca curl [--cred-id ID]" in out and "{TOKEN}" in out


def test_curl_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    code, _out, err = cca(capsys, "https://api.example.com/")
    assert code == 2 and "curl not found" in err


def test_global_config_option_before_curl(project, capsys):
    code = main(["--config", ".cca.toml", "curl", "-s", "https://api.example.com/"])
    assert code == 0 and capsys.readouterr()
    assert calls(project, "argv")[0][-1] == "--silent"


@pytest.mark.skipif(REAL_CURL is None, reason="needs the real curl")
def test_real_curl_reads_config_and_libcurl_file_redacted(project, capsys):
    """The real curl accepts the generated config; its own --libcurl output is redacted."""
    (Path("bin") / "curl").unlink()
    (Path("bin") / "curl").symlink_to(REAL_CURL)
    local = {"origins": ["https://127.0.0.1:9"], "username": USER, "password": PASSWORD}
    (project / "plain.json").write_text(json.dumps({"credentials": {"local": local}}))
    code, _out, err = cca(
        capsys, "-sS", "--libcurl", "c.c", "--connect-timeout", "5", "https://127.0.0.1:9/x"
    )
    assert code == 7, err  # connection refused: the config was read and used
    text = Path("c.c").read_text()
    assert "https://127.0.0.1:9/x" in text and '"admin:[REDACTED]"' in text
