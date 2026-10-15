"""cca entry point: version, usage, lazy subcommand import."""

import sys
import types
from importlib.metadata import version

import pytest

from cca import cli
from cca.cli import main
from cca.output import CcaError


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"cca {version('cca')}"


def test_no_command_prints_usage_and_fails(capsys):
    assert main([]) == 2
    assert "usage: cca" in capsys.readouterr().err


@pytest.fixture
def fake_commands(monkeypatch):
    """A working command `ok` and a command `broken` whose module cannot be imported."""
    mod = types.ModuleType("cca.commands.fake_ok")
    mod.add_arguments = lambda parser: parser.add_argument("--fail", action="store_true")

    def run(args):
        if args.fail:
            raise CcaError("failed on purpose", code=3)
        return 0

    mod.run = run
    monkeypatch.setitem(sys.modules, "cca.commands.fake_ok", mod)
    monkeypatch.setattr(
        cli,
        "COMMANDS",
        {"ok": ("fake_ok", "works"), "broken": ("does_not_exist_xyz", "cannot import")},
    )


def test_unselected_command_is_not_imported(fake_commands, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert main(["--config", "x.toml", "ok"]) == 0
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "cannot import" in capsys.readouterr().out
    with pytest.raises(ModuleNotFoundError):
        main(["broken"])


def test_cca_error_becomes_exit_code(fake_commands, capsys):
    assert main(["ok", "--fail"]) == 3
    assert capsys.readouterr().err == "cca: error: failed on purpose\n"
