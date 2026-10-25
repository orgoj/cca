"""cca.secrets and cca.ssh: sops shapes, fake sops, secrets never in argv or diagnostics."""

import json
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from cca import config, secrets, ssh
from cca.output import CcaError

SHAPES = Path(__file__).parent / "fixtures" / "sops-shapes"
SECRET = "s3cr3t-sentinel-value"

# file -> key the error must name (tests/fixtures/sops-shapes/README.md)
INVALID = {
    "invalid-curl-origin-bad-port.json": "credentials.example_api.origins[0]",
    "invalid-curl-origin-userinfo.json": "credentials.example_api.origins[0]",
    "invalid-curl-origin-leading-hyphen.json": "credentials.example_api.origins[0]",
    "invalid-curl-origin-trailing-hyphen.json": "credentials.example_api.origins[0]",
    "invalid-curl-http-origin.json": "credentials.example_api.origins[0]",
    "invalid-curl-origin-path.json": "credentials.example_api.origins[0]",
    "invalid-curl-duplicate-origin.json": "credentials.example_api.origins[1]",
    "invalid-curl-missing-origins.json": "credentials.example_api.origins",
    "invalid-curl-two-auth-forms.json": "credentials.example_api",
    "invalid-curl-control-char.json": "credentials.example_api.bearer",
    "invalid-curl-bad-id.json": "credentials.Example-API",
    "invalid-cloudflare-missing-token.json": "api_token",
}


def leaf_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from leaf_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from leaf_strings(value)
    elif isinstance(node, str):
        yield node


def shape_validator(name):
    return secrets.validate_cloudflare if "cloudflare" in name else secrets.validate_curl


def test_every_invalid_fixture_is_covered():
    assert sorted(p.name for p in SHAPES.glob("invalid-*.json")) == sorted(INVALID)


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_shape_names_key_never_value(name, capsys):
    path = SHAPES / name
    document = json.loads(path.read_text())
    with pytest.raises(CcaError) as exc:
        shape_validator(name)(document, path)
    message = str(exc.value)
    assert message.startswith(f"{path}: {INVALID[name]}: ")
    secret_values = [v for v in leaf_strings(document) if not v.startswith("https://")]
    output = message + capsys.readouterr().err
    assert not [v for v in secret_values if v in output]


def test_cloudflare_unknown_key_warns(capsys):
    path = SHAPES / "invalid-cloudflare-missing-token.json"
    with pytest.raises(CcaError):
        secrets.validate_cloudflare(json.loads(path.read_text()), path)
    assert f"unknown key 'token' in {path}" in capsys.readouterr().err


def test_valid_curl_normalizes_origins():
    path = SHAPES / "valid-curl.json"
    creds = secrets.validate_curl(json.loads(path.read_text()), path)
    assert creds["example_api"].origins == (
        ("https", "api.example.com", 443),
        ("https", "api.example.com", 8443),
    )
    assert creds["example_ip"].origins == (
        ("https", "203.0.113.10", 9443),
        ("https", "2001:db8::10", 443),
    )
    assert creds["example_panel"].csrf is True
    assert creds["example_panel"].password == "dummy-password"
    assert "dummy" not in repr(creds)


def test_valid_shared_origin_and_cloudflare():
    path = SHAPES / "valid-curl-shared-origin.json"
    assert len(secrets.validate_curl(json.loads(path.read_text()), path)) == 2
    path = SHAPES / "valid-cloudflare.json"
    assert secrets.validate_cloudflare(json.loads(path.read_text()), path) == (
        "dummy-cloudflare-token"
    )


# --- fake sops on PATH


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with .cca.toml, an (encrypted-looking) secrets file and a fake sops."""
    (tmp_path / ".cca.toml").write_text("schema_version = 1\n")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "cloudflare.secret.yaml").write_text("api_token: ENC[...]\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def fake_sops(project: Path, body: str) -> None:
    script = project / "bin" / "sops"
    script.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{project}/sops-argv"\n' + body + "\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def cloudflare(project: Path, capfd) -> tuple[str | None, str]:
    """(token or None, everything CCA printed incl. the error message)."""
    try:
        token = secrets.cloudflare_token(config.load())
        message = ""
    except CcaError as e:
        assert e.__cause__ is None and (e.__context__ is None or e.__suppress_context__)
        token, message = None, str(e) + repr(e)
    out, err = capfd.readouterr()
    return token, out + err + message


def test_decrypt_passes_only_the_file_path(project, capfd):
    fake_sops(project, f'echo \'{{"api_token": "{SECRET}"}}\'')
    token, printed = cloudflare(project, capfd)
    assert token == SECRET
    assert SECRET not in printed
    argv = (project / "sops-argv").read_text().splitlines()
    assert argv == ["-d", "--output-type", "json", str(project / "secrets/cloudflare.secret.yaml")]


def test_failing_sops_output_is_never_shown(project, capfd):
    fake_sops(project, f"echo '{SECRET}'; echo '{SECRET}' >&2; exit 3")
    token, printed = cloudflare(project, capfd)
    assert token is None
    assert SECRET not in printed
    assert "sops exited with status 3" in printed
    assert str(project / "secrets/cloudflare.secret.yaml") in printed


def test_malformed_json_is_never_echoed(project, capfd):
    fake_sops(project, f'echo \'{{"api_token": "{SECRET}"\'')
    token, printed = cloudflare(project, capfd)
    assert token is None
    assert SECRET not in printed
    assert "did not return a JSON object" in printed


def test_invalid_secret_value_is_never_echoed(project, capfd):
    fake_sops(project, f'echo \'{{"api_token": "{SECRET}\\\\u0007"}}\'')
    token, printed = cloudflare(project, capfd)
    assert token is None
    assert SECRET not in printed
    assert "api_token: must not contain control characters" in printed


def test_sops_missing(project, monkeypatch, capfd):
    monkeypatch.setenv("PATH", str(project / "bin"))
    token, printed = cloudflare(project, capfd)
    assert token is None and "sops not found on PATH" in printed


def test_unrunnable_sops(project, capfd):
    script = project / "bin" / "sops"
    script.write_text(f"not an executable format {SECRET}\n")
    script.chmod(0o755)
    token, printed = cloudflare(project, capfd)
    assert token is None
    assert SECRET not in printed
    assert "cannot decrypt" in printed and "cannot run" in printed


def test_secrets_file_missing(project, capfd):
    fake_sops(project, "exit 0")
    (project / "secrets" / "cloudflare.secret.yaml").unlink()
    token, printed = cloudflare(project, capfd)
    assert token is None and "secrets file not found" in printed
    assert not (project / "sops-argv").exists()


# --- ssh helper


@pytest.mark.parametrize(
    ("root", "path", "expected"),
    [
        ("C:\\proj", "C:\\proj\\secrets\\cf.yaml", True),
        ("C:\\proj", "c:\\PROJ\\secrets\\cf.yaml", True),
        ("C:\\proj", "D:\\secrets\\cf.yaml", False),  # another drive: outside, no ValueError
        ("C:\\proj", "C:\\project2\\cf.yaml", False),
        ("C:\\proj", "\\\\server\\share\\cf.yaml", False),
    ],
)
def test_secret_inside_project_on_windows_paths(root, path, expected):
    assert secrets.inside(root, path, PureWindowsPath) is expected


def test_secret_inside_project_posix():
    assert secrets.inside("/p", "/p/secrets/x", PurePosixPath)
    assert not secrets.inside("/p", "/p2/x", PurePosixPath)


def test_ssh_argv_shape(tmp_path):
    (tmp_path / ".cca.toml").write_text(
        'schema_version = 1\n[servers.server1]\nssh = "admin@server1.example.com"\n'
        "[servers.server2]\n"
    )
    cfg = config.load(str(tmp_path / ".cca.toml"))
    assert ssh.target(cfg, "server2") == "server2"
    assert ssh.argv(ssh.target(cfg, "server1"), "uptime; df -h") == [
        "ssh",
        "--",
        "admin@server1.example.com",
        "uptime; df -h",
    ]
    with pytest.raises(CcaError, match="unknown server"):
        ssh.target(cfg, "-oProxyCommand=x")
    with pytest.raises(TypeError):
        ssh.argv("server1", "true", ["evil-server"])


@pytest.mark.parametrize(
    "value", ["-oProxyCommand=x", "a b", "user@", "@host", "host;id", "host\n", ""]
)
def test_ssh_rejects_unvalidated_targets(value):
    with pytest.raises(CcaError, match="invalid ssh target"):
        ssh.argv(value, "true")
