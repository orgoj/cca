"""cca.config: doc-2 fixtures, discovery, config show."""

import os
import tomllib
from pathlib import Path

import pytest

from cca import config, validate
from cca.cli import main
from cca.commands.config import dumps
from cca.output import CcaError

FIXTURES = Path(__file__).parent / "fixtures" / "cca-toml"
VALID = sorted((FIXTURES / "valid").glob("*.toml"))
INVALID = sorted((FIXTURES / "invalid").glob("*.toml"))


def header(path: Path, tag: str) -> str:
    first = path.read_text().splitlines()[0]
    assert first.startswith(f"# {tag}: "), path
    return first.removeprefix(f"# {tag}: ")


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_loads(path, capsys):
    cfg = config.load(str(path))
    assert cfg.data["schema_version"] == 1
    warned = [
        line.split("'")[1] for line in capsys.readouterr().err.splitlines() if "unknown key" in line
    ]
    expected = header(path, "warn").split(", ") if path.name == "unknown-key.toml" else []
    assert sorted(warned) == sorted(expected)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_fails_naming_key(path):
    expect = header(path, "expect")
    with pytest.raises(CcaError) as exc:
        config.load(str(path))
    assert exc.value.code == 2
    message = str(exc.value)
    assert message.startswith(f"{path}: ")
    assert ("syntax error" if expect == "syntax" else f": {expect}: ") in message


def test_future_schema_names_both_versions():
    with pytest.raises(CcaError, match=r"999 is newer .* \(1\)"):
        config.load(str(FIXTURES / "invalid" / "future-schema-version.toml"))


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_lower_schema_version_fails(tmp_path):
    with pytest.raises(CcaError, match="schema_version: must be at least 1"):
        config.load(str(write(tmp_path / ".cca.toml", "schema_version = 0\n")))


def test_defaults_filled(tmp_path):
    cfg = config.load(str(write(tmp_path / ".cca.toml", "schema_version = 1\n[servers.server1]\n")))
    assert cfg.data["servers"] == {
        "server1": {"ssh": "server1", "netdata_port": 19999, "netdata_transport": "ssh"}
    }
    assert cfg.data["run"] == {"transport": "tmux", "tokf": False, "tmux": {}}
    assert cfg.data["secrets"]["curl"] == "secrets/curl.secret.yaml"
    assert cfg.data["server_info"]["net_iface_prefixes"] == ["en", "eth"]
    assert cfg.resolve(cfg.data["secrets"]["curl"]) == tmp_path / "secrets/curl.secret.yaml"


def test_operator_at_name_limit(tmp_path):
    text = f'schema_version = 1\n[run.log]\noperator = "{"a" * 64}"\n'
    assert config.load(str(write(tmp_path / ".cca.toml", text))).data["run"]["log"]["dir"] == "logs"


def test_full_fixture_values():
    cfg = config.load(str(FIXTURES / "valid" / "full.toml"))
    assert list(cfg.data["servers"]) == ["server1", "server2", "server3"]
    assert cfg.data["servers"]["server3"]["ssh"] == "server3"
    assert cfg.data["run"]["log"] == {"dir": "logs", "operator": "admin1"}


def test_use_time_errors(tmp_path):
    cfg = config.load(str(write(tmp_path / ".cca.toml", "schema_version = 1\n")))
    with pytest.raises(CcaError, match=r"run\.tmux\.session: required by this command"):
        cfg.require("run.tmux.session")
    with pytest.raises(CcaError, match=r"unknown server 'server1' \(servers: none\)"):
        cfg.server("server1")


# --- discovery


@pytest.fixture
def tree(tmp_path):
    project = tmp_path / "project"
    write(project / ".cca.toml", "schema_version = 1\n[servers.parent]\n")
    (project / "a" / "b").mkdir(parents=True)
    return project


def test_discovery_exact_cwd(tree, monkeypatch):
    monkeypatch.chdir(tree)
    assert config.load().path == tree / ".cca.toml"


def test_discovery_from_descendant(tree, monkeypatch):
    monkeypatch.chdir(tree / "a" / "b")
    assert config.load().path == tree / ".cca.toml"


def test_discovery_nested_shadow(tree, monkeypatch):
    write(tree / "a" / ".cca.toml", "schema_version = 1\n[servers.nested]\n")
    monkeypatch.chdir(tree / "a" / "b")
    cfg = config.load()
    assert cfg.path == tree / "a" / ".cca.toml"
    assert list(cfg.data["servers"]) == ["nested"]


def test_discovery_none_found(tmp_path, monkeypatch, capsys):
    if any(os.path.lexists(p / ".cca.toml") for p in tmp_path.parents if p != Path("/")):
        pytest.skip("a .cca.toml exists above the pytest tmp dir")
    monkeypatch.chdir(tmp_path)
    assert config.load() is None
    assert main(["config", "show"]) == 2
    assert "no .cca.toml found" in capsys.readouterr().err


def test_discovery_malformed_nearest_never_falls_back(tree, monkeypatch):
    write(tree / "a" / ".cca.toml", "schema_version = \n")
    monkeypatch.chdir(tree / "a" / "b")
    with pytest.raises(CcaError, match="syntax error"):
        config.load()


def test_discovery_unreadable_nearest_never_falls_back(tree, monkeypatch):
    (tree / "a" / ".cca.toml").mkdir()
    monkeypatch.chdir(tree / "a" / "b")
    with pytest.raises(CcaError, match="cannot read"):
        config.load()


def test_discovery_broken_link_nearest_never_falls_back(tree, monkeypatch):
    (tree / "a" / ".cca.toml").symlink_to(tree / "missing.toml")
    monkeypatch.chdir(tree / "a" / "b")
    with pytest.raises(CcaError, match="cannot read"):
        config.load()


def test_discovery_stops_before_filesystem_root():
    assert config.find("/") is None


def test_discovery_uses_physical_cwd(tree, tmp_path, monkeypatch):
    other = tmp_path / "other"
    write(other / ".cca.toml", "schema_version = 1\n[servers.logical]\n")
    (other / "link").symlink_to(tree / "a" / "b")
    monkeypatch.chdir(other / "link")
    monkeypatch.setenv("PWD", str(other / "link"))
    assert config.load().path == tree / ".cca.toml"


def test_config_option_resolves_from_cwd(tree, tmp_path, monkeypatch):
    write(tmp_path / "alt" / "x.toml", "schema_version = 1\n")
    monkeypatch.chdir(tmp_path / "alt")
    assert config.load("x.toml").path == tmp_path / "alt" / "x.toml"
    with pytest.raises(CcaError, match="cannot read"):
        config.load("missing.toml")


# --- config show


def test_config_show_prints_path_and_roundtrips(capsys):
    path = FIXTURES / "valid" / "full.toml"
    assert main(["--config", str(path), "config", "show"]) == 0
    out = capsys.readouterr().out
    first, _, body = out.partition("\n")
    assert first == f"# {path}"
    assert tomllib.loads(body) == config.load(str(path)).data


def test_dumps_quotes_special_strings():
    data = {"a": {"s": 'x"y\\z', "l": ["en"], "b": True, "i": 3}, "empty": {}}
    assert tomllib.loads(dumps(data)) == data


# --- HTTPS URL rules (doc-2)


@pytest.mark.parametrize(
    ("url", "origin", "tail"),
    [
        ("HTTPS://API.Example.COM./v4", ("https", "api.example.com", 443), "/v4"),
        ("https://[2001:DB8:0::1]:8443", ("https", "2001:db8::1", 8443), ""),
        ("https://203.0.113.5?x", ("https", "203.0.113.5", 443), "?x"),
    ],
)
def test_https_url_normalization(url, origin, tail):
    assert validate.parse_https_url(url) == (origin, tail)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user@example.com",
        "https://example.com:0",
        "https://example.com:65536",
        "https://example.com:",
        "https://-example.com",
        "https://exa mple.com",
        "https://example..com",
        "https://[::1",
        "https://",
        "https://example.com\\@x",
        "https://example.com:１",
    ],
)
def test_https_url_rejected(url):
    with pytest.raises(ValueError):
        validate.parse_https_url(url)
