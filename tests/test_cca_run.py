"""cca run and cca.executor: fake ssh on PATH; the tmux transport against a real tmux
server on a private socket (skipped without tmux), its "ssh" a local bash."""

import base64
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

import pytest

from cca import executor
from cca.cli import main

TMUX = shutil.which("tmux")
SERVERS = (
    '[servers.server1]\nssh = "admin@host1"\n'
    '[servers.server2]\nssh = "host2"\n'
    '[servers.server3]\nssh = "fail"\n'
)


def write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Project dir with a .cca.toml helper, PATH = only fake tools, no ambient tmux."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "work").mkdir()
    (tmp_path / "remote").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    # fake ssh: logs argv; with a remote command runs it under /bin/sh -c (a POSIX login
    # shell) in remote/, without one starts an interactive bash (the tmux pane)
    write_exe(
        tmp_path / "bin" / "ssh",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{tmp_path}/ssh.log"\n'
        '[ "$1" = "--" ] || exit 99\n'
        f'cd "{tmp_path}/remote"\n'
        'if [ $# -eq 3 ]; then exec /usr/bin/env -i PATH=/usr/bin:/bin CCA_TARGET="$2" '
        '/bin/sh -c "$3"; fi\n'
        'exec /usr/bin/env -i PATH=/usr/bin:/bin HOME=/tmp TERM=xterm CCA_TARGET="$2" '
        "PS1='$ ' /bin/bash --norc --noprofile -i\n",
    )
    return tmp_path


def project(env: Path, run: str = 'transport = "ssh"\n', extra: str = "") -> None:
    (env / "work" / ".cca.toml").write_text(f"schema_version = 1\n{SERVERS}[run]\n{run}{extra}")


def ssh_calls(env: Path) -> list[str]:
    log = env / "ssh.log"
    return log.read_text().splitlines() if log.exists() else []


class Stdin(io.TextIOWrapper):
    def __init__(self, data: bytes, tty: bool = False):
        super().__init__(io.BytesIO(data))
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def cca(argv: list[str], monkeypatch, stdin: bytes | None = None, tty: bool = False) -> int:
    monkeypatch.setattr(sys, "stdin", Stdin(stdin or b"", tty))
    return main(["run", *argv])


@pytest.fixture(autouse=True)
def no_local_shell(monkeypatch):
    """Every child cca starts is an argv for ssh, tmux or tokf: never a shell."""
    real = subprocess.Popen.__init__

    def guarded(self, args, *a, **kw):
        assert not kw.get("shell"), args
        assert isinstance(args, list), args
        assert os.path.basename(args[0]) in ("ssh", "tmux", "tokf"), args
        real(self, args, *a, **kw)

    monkeypatch.setattr(subprocess.Popen, "__init__", guarded)


# --- argument shape (public contract)


@pytest.mark.parametrize(
    "argv, message",
    [
        ([], "-t SERVER required"),
        (["--", "uptime"], "-t SERVER required"),
        (["server1", "--", "id"], "-t SERVER required"),
        (["-t", "server1", "uptime"], "the server goes after -t"),
        (["-t", "server1", "server2", "--", "id"], "the server goes after -t"),
        (["-t", "server1", "--"], "no command after --"),
        (["-t"], "-t needs a value"),
        (["-t", "server1", "-t", "server2"], "-t given twice"),
        (["--bogus", "-t", "server1"], "unknown option '--bogus'"),
        (["--timeout", "0", "-t", "server1"], "--timeout must be an integer 1-86400"),
        (["--timeout", "x", "-t", "server1"], "--timeout must be an integer"),
        (["--timeout"], "--timeout needs a value"),
        (["--timeout", "5", "--timeout", "6", "-t", "server1"], "--timeout given twice"),
        (["--all", "server1", "--", "id"], "the server goes after -t"),
        (["--all", "-t", "server1", "--", "id"], "-t cannot be combined with --all"),
        (["--create-file", "/tmp/x", "-t", "server1", "--", "id"], "-t cannot be combined"),
        (["-t", "server1", "--create-file", "/tmp/x", "--", "id"], "-t cannot be combined"),
        (["--read", "-t", "server1"], "-t cannot be combined with --read"),
        (["--list", "-t", "server1"], "-t cannot be combined with --list"),
        (["--session", "-t", "server1"], "-t cannot be combined with --session"),
        (["--list", "server1"], "--list takes no SERVER"),
        (["--list", "--all"], "--list and --all cannot be combined"),
        (["--read"], "--read needs exactly one SERVER"),
        (["--read", "server1", "server2"], "--read needs exactly one SERVER"),
        (["--read", "server1", "--", "id"], "takes no command"),
        (["--lines", "5", "server1"], "--lines needs --read"),
        (["--read", "--lines", "5", "--scrollback", "server1"], "cannot be combined"),
        (["--read", "--marker", "x;rm", "server1"], "invalid marker"),
        (["--read", "--timeout", "5", "server1"], "--timeout does not apply to --read"),
        (["--create-file", "/tmp/x"], "--create-file needs exactly one SERVER"),
        (["--create-file", "/tmp/x", "server1", "--", "id"], "takes no command"),
        (["--session", "server1", "-x"], "no command and no options"),
    ],
)
def test_usage_errors(env, monkeypatch, capsys, argv, message):
    project(env)
    assert cca(argv, monkeypatch, b"id\n") == 2
    assert message in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_help(env, monkeypatch, capsys):
    assert cca(["--help"], monkeypatch) == 0
    out = capsys.readouterr().out
    assert "cca run [--timeout SEC] -t SERVER [-- CMD...]" in out
    assert "--create-file PATH" in out


def test_unknown_server(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server9;id", "--", "id"], monkeypatch) == 2
    assert "unknown server 'server9;id'" in capsys.readouterr().err
    assert ssh_calls(env) == []


@pytest.mark.parametrize("name", ["a;b", "-oProxyCommand=x", "a b", "$(id)"])
def test_malicious_server_name_rejected_at_load(env, monkeypatch, capsys, name):
    (env / "work" / ".cca.toml").write_text(f'schema_version = 1\n[servers."{name}"]\n')
    assert cca(["-t", name, "--", "id"], monkeypatch) == 2
    assert "server name must match" in capsys.readouterr().err
    assert ssh_calls(env) == []


@pytest.mark.parametrize("target", ["-oProxyCommand=touch x", "a b", "h;id", "u@-h"])
def test_malicious_ssh_target_rejected_at_load(env, monkeypatch, capsys, target):
    (env / "work" / ".cca.toml").write_text(
        f'schema_version = 1\n[servers.server1]\nssh = "{target}"\n'
    )
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 2
    assert "servers.server1.ssh" in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_no_config(env, monkeypatch, capsys):
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 2
    assert "no .cca.toml found" in capsys.readouterr().err


# --- command from stdin


def test_tty_stdin_without_command(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1"], monkeypatch, tty=True) == 2
    assert "stdin is a terminal" in capsys.readouterr().err


@pytest.mark.parametrize("data", [b"", b"  \n\n"])
def test_empty_stdin_without_command(env, monkeypatch, capsys, data):
    project(env)
    assert cca(["-t", "server1"], monkeypatch, data) == 2
    assert "empty command on stdin" in capsys.readouterr().err


def test_command_too_long(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1"], monkeypatch, b"x" * (executor.COMMAND_MAX + 1)) == 2
    assert "longer than" in capsys.readouterr().err


# --- ssh transport


def decoded(remote: str) -> str:
    """The command inside the remote form `bash -c "$(printf %s B64 | base64 -d)" ...`."""
    b64 = remote.split("printf %s ", 1)[1].split(" ", 1)[0]
    return base64.b64decode(b64).decode()


def test_ssh_run_argv_and_output(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1", "--", "echo", "hello;", "echo", "$CCA_TARGET"], monkeypatch) == 0
    assert capsys.readouterr().out == "hello\nadmin@host1\n"
    (line,) = ssh_calls(env)
    assert line.startswith("-- admin@host1 bash -c ")
    assert line.endswith(" </dev/null")
    assert decoded(line) == "echo hello; echo $CCA_TARGET"  # joined with spaces, like ssh


def test_ssh_exit_code_and_stderr(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server2", "--", "echo out; echo err >&2; exit 7"], monkeypatch) == 7
    assert capsys.readouterr().out == "out\nerr\n"


def test_ssh_stdin_command_multiline(env, monkeypatch, capsys):
    project(env)
    script = b"cat <<'EOF'\nquote ' \" $HOME `x`\nEOF\nprintf 'no newline'"
    assert cca(["-t", "server1"], monkeypatch, script) == 0
    assert capsys.readouterr().out == "quote ' \" $HOME `x`\nno newline"


@pytest.mark.parametrize(
    "command",
    ["$(touch pwned)", "`touch pwned`", "; touch pwned", "' ; touch pwned ; '", "a\nb\x07"],
)
def test_ssh_malicious_command_reaches_remote_verbatim(env, monkeypatch, command):
    project(env)
    cca(["-t", "server1", "--", command], monkeypatch)
    (line,) = ssh_calls(env)
    assert decoded(line) == command
    assert not (env / "work" / "pwned").exists()  # nothing ran locally


def test_ssh_remote_stdin_is_devnull(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1", "--", "cat; echo done"], monkeypatch) == 0
    assert capsys.readouterr().out == "done\n"


def test_command_after_dashes_never_reads_local_stdin(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1", "--", "echo", "--timeout", "5"], monkeypatch, b"rm -rf /\n") == 0
    assert capsys.readouterr().out == "--timeout 5\n"  # words after -- are the command
    assert sys.stdin.read() == "rm -rf /\n"  # left unread


def test_ssh_output_control_characters_escaped(env, monkeypatch, capsys):
    project(env)
    assert cca(["-t", "server1", "--", r"printf 'a\033[2Jb\tc\n'"], monkeypatch) == 0
    assert capsys.readouterr().out == "a\\x1b[2Jb\tc\n"


def test_ssh_timeout(env, monkeypatch, capsys):
    project(env)
    started = time.monotonic()
    assert (
        cca(["--timeout", "1", "-t", "server1", "--", "echo early; sleep 10"], monkeypatch) == 124
    )
    assert time.monotonic() - started < 5
    captured = capsys.readouterr()
    assert captured.out == "early\n"
    assert "did not finish within 1s, ssh was stopped" in captured.err


def test_ssh_output_limit_stops_endless_output(env, monkeypatch, capsys):
    project(env)
    monkeypatch.setattr(executor, "OUTPUT_MAX", 100_000)
    started = time.monotonic()
    assert cca(["-t", "server1", "--", "yes x"], monkeypatch) == executor.OUTPUT_LIMIT_EXIT
    assert time.monotonic() - started < 10  # killed on overflow, not at the 300 s timeout
    captured = capsys.readouterr()
    assert captured.out == ""  # the partial output is discarded
    assert "server1: output exceeded 100000 bytes, ssh stopped" in captured.err


def test_ssh_output_limit_boundary(env, monkeypatch, capsys):
    project(env)
    monkeypatch.setattr(executor, "OUTPUT_MAX", 1000)
    assert cca(["-t", "server1", "--", "head -c 1000 /dev/zero | tr '\\0' a"], monkeypatch) == 0
    assert capsys.readouterr().out == "a" * 1000
    code = cca(["-t", "server1", "--", "head -c 1001 /dev/zero | tr '\\0' a"], monkeypatch)
    assert code == executor.OUTPUT_LIMIT_EXIT
    assert "output exceeded" in capsys.readouterr().err


def test_ssh_output_limit_logged_and_stops_all(env, monkeypatch, capsys):
    project(env, extra='[run.log]\ndir = "logs"\noperator = "tester"\n')
    (env / "work" / "logs").mkdir()
    monkeypatch.setattr(executor, "OUTPUT_MAX", 1000)
    assert cca(["--all", "--", "yes x"], monkeypatch) == executor.OUTPUT_LIMIT_EXIT
    assert len(ssh_calls(env)) == 1  # server2 and server3 never contacted
    (log,) = (env / "work" / "logs").iterdir()
    assert "output-limit" in log.read_text()


@pytest.mark.parametrize("argv", [["--read", "server1"], ["--session"]])
def test_tmux_surfaces_rejected_over_ssh(env, monkeypatch, capsys, argv):
    project(env)
    assert cca(argv, monkeypatch) == 2
    assert 'not available with run.transport = "ssh"' in capsys.readouterr().err


def test_list_ssh(env, monkeypatch, capsys):
    project(env)
    assert cca(["--list"], monkeypatch) == 0
    assert capsys.readouterr().out == "server1\tadmin@host1\nserver2\thost2\nserver3\tfail\n"


def test_alias_resolves_to_its_entry_and_never_repeats_in_all(env, monkeypatch, capsys):
    (env / "work" / ".cca.toml").write_text(
        'schema_version = 1\n[servers.web-gen2]\nssh = "host2"\naliases = ["web"]\n'
        '[servers.web-gen1]\nssh = "host1"\n[run]\ntransport = "ssh"\n[run.log]\n'
        'operator = "admin1"\n'
    )
    (env / "work" / "logs").mkdir()
    assert cca(["-t", "web", "--", "echo $CCA_TARGET"], monkeypatch) == 0
    captured = capsys.readouterr()
    assert captured.out == "host2\n" and "note: web is an alias of web-gen2" in captured.err
    (log,) = (env / "work" / "logs").iterdir()
    assert " admin1 web-gen2 echo $CCA_TARGET" in log.read_text()  # the real entry
    assert cca(["--all", "--", "true"], monkeypatch) == 0
    out = capsys.readouterr().out
    assert out.count("<server-result") == 2 and 'name="web"' not in out
    assert cca(["--list"], monkeypatch) == 0
    assert capsys.readouterr().out == "web-gen2\thost2\taliases=web\nweb-gen1\thost1\n"
    assert cca(["-t", "nope", "--", "true"], monkeypatch) == 2
    assert "servers: web-gen2 (web), web-gen1" in capsys.readouterr().err


def test_all_order_and_stop_on_failure(env, monkeypatch, capsys):
    project(env)
    command = 'echo "on $CCA_TARGET"; [ "$CCA_TARGET" != host2 ]'
    assert cca(["--all", "--", command], monkeypatch) == 1
    assert capsys.readouterr().out == (
        '<server-result name="server1" exit="0">\non admin@host1\n</server-result>\n'
        '<server-result name="server2" exit="1">\non host2\n</server-result>\n'
    )
    assert [line.split()[1] for line in ssh_calls(env)] == ["admin@host1", "host2"]


def test_all_from_stdin(env, monkeypatch, capsys):
    project(env)
    assert cca(["--all"], monkeypatch, b"echo $CCA_TARGET\n") == 0
    out = capsys.readouterr().out
    assert out.count("<server-result") == 3
    assert out.index("admin@host1") < out.index("host2") < out.index("fail")


def test_all_without_servers(env, monkeypatch, capsys):
    (env / "work" / ".cca.toml").write_text('schema_version = 1\n[run]\ntransport = "ssh"\n')
    assert cca(["--all", "--", "id"], monkeypatch) == 2
    assert "no [servers] configured" in capsys.readouterr().err


# --- --create-file


def test_create_file_ssh_new_and_existing(env, monkeypatch, capsys):
    project(env)
    target = env / "remote" / "out.txt"
    content = b"line1\n\x00binary'\"$x\nno newline"
    assert cca(["--create-file", str(target), "server1"], monkeypatch, content) == 0
    assert target.read_bytes() == content
    assert str(target) in capsys.readouterr().out
    target.chmod(0o640)
    assert cca(["--create-file", str(target), "server1"], monkeypatch, b"") == 0
    assert target.read_bytes() == b""
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert [p.name for p in (env / "remote").iterdir()] == ["out.txt"]  # no temp files left


def test_create_file_relative_path(env, monkeypatch, capsys):
    project(env)
    assert cca(["--create-file", "-x/y", "server1"], monkeypatch, b"x") == 2
    assert "must be absolute" in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_create_file_missing_dir(env, monkeypatch, capsys):
    project(env)
    target = env / "remote" / "missing" / "f"
    assert cca(["--create-file", str(target), "server1"], monkeypatch, b"x") != 0
    assert not target.exists()


def test_create_file_tty_stdin(env, monkeypatch, capsys):
    project(env)
    assert cca(["--create-file", "/tmp/x", "server1"], monkeypatch, tty=True) == 2
    assert "stdin is a terminal" in capsys.readouterr().err


# --- command log


def test_log_lines(env, monkeypatch, capsys):
    project(env, extra='[run.log]\ndir = "logs"\noperator = "admin1"\n')
    (env / "work" / "logs").mkdir()
    cca(["-t", "server1", "--", "mysql --password hunter2 -e 'select 1'\nexit 3"], monkeypatch)
    cca(["--create-file", str(env / "remote" / "f"), "server2"], monkeypatch, b"x")
    (log,) = (env / "work" / "logs").iterdir()
    assert log.name.endswith("-admin1.log")
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    first, second = log.read_text().splitlines()
    stamp, operator, server, rest = first.split(" ", 3)
    assert time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
    assert (operator, server) == ("admin1", "server1")
    assert rest == "mysql --password [REDACTED] -e 'select 1'\\nexit 3 [exit: 3]"
    assert second.endswith(f"admin1 server2 create-file {env}/remote/f [exit: 0]")


@pytest.mark.parametrize(
    "command, logged",
    [
        ("curl https://user:pw@example.com/", "curl https://[USER]:[REDACTED]@example.com/"),
        ("export TOKEN=abc123", "export TOKEN=[REDACTED]"),
        ('api_key: "a b c"', 'api_key: "[REDACTED]"'),
        ("x AKIAABCDEFGHIJKLMNOP", "x AKIA[REDACTED]"),
        ("curl -H 'Authorization: Bearer abc.def'", "curl -H 'Authorization: Bearer [REDACTED]'"),
        ("mongosh mongodb://u:p@h/db", "mongosh mongodb://[REDACTED]"),
        ("echo " + "A" * 44, "echo [BASE64_REDACTED]"),
        ("uptime", "uptime"),
    ],
)
def test_sanitize(command, logged):
    assert executor.sanitize(command) == logged


def test_log_dir_missing_runs_nothing(env, monkeypatch, capsys):
    project(env, extra='[run.log]\noperator = "admin1"\n')
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 2
    assert "run.log.dir" in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_log_operator_defaults_to_os_login(env, monkeypatch, capsys):
    project(env, extra='[run.log]\ndir = "logs"\n')
    (env / "work" / "logs").mkdir()
    monkeypatch.setattr(executor, "login_name", lambda: "admin2")
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 0
    (log,) = (env / "work" / "logs").iterdir()
    assert log.name.endswith("-admin2.log")
    assert " admin2 server1 id [exit: 0]" in log.read_text()


def test_log_explicit_operator_never_reads_os_login(env, monkeypatch, capsys):
    project(env, extra='[run.log]\ndir = "logs"\noperator = "admin1"\n')
    (env / "work" / "logs").mkdir()

    def boom():
        raise AssertionError("OS login looked up")

    monkeypatch.setattr(executor, "login_name", boom)
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 0
    assert next((env / "work" / "logs").iterdir()).name.endswith("-admin1.log")


@pytest.mark.parametrize(
    ("login", "message"),
    [
        (KeyError("getpwuid(): uid not found: 4242"), "cannot read the OS login name"),
        (OSError("GetUserNameW failed"), "cannot read the OS login name (GetUserNameW failed)"),
        ("DOMAIN\\user\x1b", "the OS login name 'DOMAIN\\\\user\\x1b' is not a valid operator"),
        ("a" * 65, "is not a valid operator"),
    ],
)
def test_log_unusable_os_login_runs_nothing(env, monkeypatch, capsys, login, message):
    project(env, extra='[run.log]\ndir = "logs"\n')
    (env / "work" / "logs").mkdir()

    def lookup():
        if isinstance(login, Exception):
            raise login
        return login

    monkeypatch.setattr(executor, "login_name", lookup)
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 2
    err = capsys.readouterr().err
    assert "run.log.operator: " in err and message in err and "set operator" in err
    assert "\x1b" not in err
    assert ssh_calls(env) == []
    assert list((env / "work" / "logs").iterdir()) == []


def test_login_name_posix_uses_passwd_not_env(monkeypatch):
    pwd = pytest.importorskip("pwd")
    monkeypatch.setenv("USER", "someone-else")
    monkeypatch.setenv("LOGNAME", "someone-else")
    assert executor.login_name() == pwd.getpwuid(os.getuid()).pw_name


@pytest.mark.parametrize("ok", [True, False])
def test_login_name_windows(monkeypatch, ok):
    """Without pwd (Windows) the name comes from GetUserNameW; failure raises OSError."""
    import builtins
    import ctypes

    real_import = builtins.__import__

    def no_pwd(name, *args, **kwargs):
        if name == "pwd":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    def get_user_name(buffer, size):
        buffer.value = "winadmin"
        return 1 if ok else 0

    windll = types.SimpleNamespace(advapi32=types.SimpleNamespace(GetUserNameW=get_user_name))
    monkeypatch.setattr(builtins, "__import__", no_pwd)
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)
    if ok:
        assert executor.login_name() == "winadmin"
    else:
        with pytest.raises(OSError, match="GetUserNameW failed"):
            executor.login_name()


def test_log_symlink_not_followed(env, monkeypatch, capsys):
    project(env, extra='[run.log]\ndir = "logs"\noperator = "admin1"\n')
    (env / "work" / "logs").mkdir()
    victim = env / "victim"
    victim.write_text("keep\n")
    today = time.strftime("%Y-%m-%d")
    (env / "work" / "logs" / f"{today}-admin1.log").symlink_to(victim)
    assert cca(["-t", "server1", "--", "exit 4"], monkeypatch) == 4
    assert "cannot write command log" in capsys.readouterr().err
    assert victim.read_text() == "keep\n"


# --- tokf


def fake_tokf(env: Path, probe: int = 0, process: int = 0) -> None:
    write_exe(
        env / "bin" / "tokf",
        "#!/bin/sh\n"
        f'[ "$2" = --supports-protocol ] && exit {probe}\n'
        f'printf "%s\\n" "$*" > "{env}/tokf.args"\n'
        f'/bin/cat > "{env}/tokf.in"\n'
        f"echo processed; exit {process}\n",
    )


def test_tokf_processes_output(env, monkeypatch, capsys):
    project(env, run='transport = "ssh"\ntokf = true\n')
    fake_tokf(env)
    assert cca(["-t", "server1", "--", "echo raw; exit 5"], monkeypatch) == 5
    assert capsys.readouterr().out == "processed\n"
    assert (env / "tokf.in").read_text() == "raw\n"
    assert (env / "tokf.args").read_text() == (
        "process --protocol cca-v1 --return-processor-status --command echo raw; exit 5 "
        "--exit-code 5\n"
    )


@pytest.mark.parametrize("probe, process", [(1, 0), (0, 3)])
def test_tokf_fallback_raw(env, monkeypatch, capsys, probe, process):
    project(env, run='transport = "ssh"\ntokf = true\n')
    fake_tokf(env, probe, process)
    assert cca(["-t", "server1", "--", "echo raw"], monkeypatch) == 0
    assert capsys.readouterr().out == "raw\n"


def test_tokf_off_by_default(env, monkeypatch, capsys):
    project(env)
    fake_tokf(env)
    assert cca(["-t", "server1", "--", "echo raw"], monkeypatch) == 0
    assert capsys.readouterr().out == "raw\n"
    assert not (env / "tokf.in").exists()


# --- marker parsing (cases of the former tmux_cli_python tests)

M = "CCA_1_2"


@pytest.mark.parametrize(
    "end, code",
    [
        ("EXITCODE=0", 0),
        ("EXITCODE=42", 42),
        ("INTERRUPTED", 130),
        ("TERMINATED", 143),
        ("HANGUP", 129),
        ("KILLED", 137),
    ],
)
def test_marker_block_exit_codes(end, code):
    text = f"before\n=== START {M} ===\nline 1\nline 2\n\n=== END {M} {end} ===\n$ "
    assert executor.marker_block(text, M) == (["line 1", "line 2", ""], code)


def test_marker_block_missing_and_running():
    assert executor.marker_block("no markers", M) is None
    assert executor.marker_block(f"=== START {M} ===\nrunning", M) == (["running"], None)


def test_marker_block_uses_last_start_and_ignores_other_markers():
    text = (
        f"=== START {M} ===\nold\n=== END {M} EXITCODE=1 ===\n"
        f"=== START {M} ===\n=== END CCA_9_9 EXITCODE=0 ===\nnew\n=== END {M} EXITCODE=0 ===\n"
    )
    assert executor.marker_block(text, M) == (["=== END CCA_9_9 EXITCODE=0 ===", "new"], 0)


def test_marker_block_typed_line_is_not_a_marker():
    """The echoed typed command contains the marker but never as a complete marker line."""
    line = executor._typed_line(M, "echo hi", None)
    assert executor.marker_block(line, M) is None
    assert not executor._end_re(M).search(line)


# --- tmux transport (real tmux on a private socket)


@pytest.fixture
def tmux_env(env, monkeypatch):
    if TMUX is None:
        pytest.skip("tmux not installed")
    os.symlink(TMUX, env / "bin" / "tmux")
    sock = tempfile.mkdtemp(prefix="cca-tmux-")  # short: socket paths are length-limited
    monkeypatch.setenv("TMUX_TMPDIR", sock)
    monkeypatch.setattr(executor, "SSH_SETTLE", 0.5)
    monkeypatch.setattr(executor, "POLL", 0.05)
    project(env, run='transport = "tmux"\n[run.tmux]\nsession = "cca-test"\n')
    yield env
    subprocess.run([TMUX, "kill-server"], capture_output=True, env={**os.environ})
    shutil.rmtree(sock, ignore_errors=True)


def tmux_out(*args: str) -> str:
    return subprocess.run([TMUX, *args], capture_output=True, text=True).stdout


def test_tmux_run_opens_window_and_returns_output(tmux_env, monkeypatch, capsys):
    assert cca(["-t", "server1", "--", "echo hello $CCA_TARGET; exit 3"], monkeypatch) == 3
    assert capsys.readouterr().out == "hello admin@host1\n"
    assert ssh_calls(tmux_env) == ["-- admin@host1"]  # window: ssh -- TARGET, no shell
    assert tmux_out("list-windows", "-t", "=cca-test", "-F", "#{window_name}") == "server1\n"
    assert cca(["-t", "server1", "--", "echo again"], monkeypatch) == 0  # window reused
    assert capsys.readouterr().out == "again\n"
    assert len(ssh_calls(tmux_env)) == 1


def test_tmux_multiline_stdin_and_quotes(tmux_env, monkeypatch, capsys):
    script = b"cat <<'EOF'\nquote ' \" $HOME `x` ;\nEOF\nprintf 'no newline'\n"
    assert cca(["-t", "server1"], monkeypatch, script) == 0
    assert capsys.readouterr().out == "quote ' \" $HOME `x` ;\nno newline\n"


def test_tmux_large_command(tmux_env, monkeypatch, capsys):
    """Over the tmux send-keys argument limit (about 16 KB)."""
    command = "x=" + "a" * 30000 + "; echo ${#x}"
    assert cca(["-t", "server1", "--", command], monkeypatch) == 0
    assert capsys.readouterr().out == "30000\n"


def test_tmux_remote_stdin_is_devnull(tmux_env, monkeypatch, capsys):
    assert cca(["--timeout", "10", "-t", "server1", "--", "cat; echo done"], monkeypatch) == 0
    assert capsys.readouterr().out == "done\n"


@pytest.mark.parametrize("signal, code", [("INT", 130), ("TERM", 143), ("HUP", 129), ("KILL", 137)])
def test_tmux_signal_markers(tmux_env, monkeypatch, capsys, signal, code):
    assert (
        cca(["-t", "server1", "--", f"echo before; kill -{signal} $$; echo after"], monkeypatch)
        == code
    )
    assert capsys.readouterr().out == "before\n"


def test_tmux_pane_shell_survives_signals(tmux_env, monkeypatch, capsys):
    assert cca(["-t", "server1", "--", "kill -INT $$"], monkeypatch) == 130
    assert cca(["-t", "server1", "--", "echo alive"], monkeypatch) == 0
    assert capsys.readouterr().out == "alive\n"


def test_tmux_timeout_then_read_marker(tmux_env, monkeypatch, capsys):
    assert (
        cca(
            ["--timeout", "1", "-t", "server1", "--", "echo early; sleep 2; echo late"], monkeypatch
        )
        == 124
    )
    captured = capsys.readouterr()
    assert captured.out == "early\n"
    marker = captured.err.split("--marker ")[1].split()[0]
    assert executor.MARKER_RE.fullmatch(marker)
    assert "it may still run" in captured.err
    assert cca(["--read", "--marker", marker, "server1"], monkeypatch) == 124
    assert capsys.readouterr().out == "early\n"
    time.sleep(2)
    assert cca(["--read", "--marker", marker, "server1"], monkeypatch) == 0
    assert capsys.readouterr().out == "early\nlate\n"


def test_tmux_read_variants(tmux_env, monkeypatch, capsys):
    assert cca(["-t", "server1", "--", "seq 1 300"], monkeypatch) == 0
    capsys.readouterr()
    assert cca(["--read", "server1"], monkeypatch) == 0
    visible = capsys.readouterr().out
    assert "300" in visible and "\n1\n" not in visible
    assert cca(["--read", "--scrollback", "server1"], monkeypatch) == 0
    assert "\n1\n" in capsys.readouterr().out
    assert cca(["--read", "--lines", "5", "server1"], monkeypatch) == 0
    assert "300" in capsys.readouterr().out


def test_tmux_read_without_window(tmux_env, monkeypatch, capsys):
    assert cca(["--read", "server2"], monkeypatch) == 2
    assert "no tmux window for server2" in capsys.readouterr().err
    assert ssh_calls(tmux_env) == []


def test_tmux_list_and_session(tmux_env, monkeypatch, capsys):
    assert cca(["--list"], monkeypatch) == 0
    assert capsys.readouterr().out == (
        "server1\tadmin@host1\t-\nserver2\thost2\t-\nserver3\tfail\t-\n"
    )
    assert cca(["--session", "server2"], monkeypatch) == 0
    assert capsys.readouterr().out == "server2\topened\nattach: tmux attach -t =cca-test\n"
    assert cca(["--session"], monkeypatch) == 0
    assert capsys.readouterr().out == (
        "server1\topened\nserver2\topen\nserver3\topened\nattach: tmux attach -t =cca-test\n"
    )
    assert cca(["--list"], monkeypatch) == 0
    assert capsys.readouterr().out.count("\twindow\n") == 3


def test_tmux_session_name_exact(tmux_env, monkeypatch, capsys):
    """=SESSION: an existing session whose name only starts with ours is not used."""
    subprocess.run([TMUX, "new-session", "-d", "-s", "cca-test-other"], check=True)
    assert cca(["-t", "server1", "--", "echo x"], monkeypatch) == 0
    sessions = tmux_out("list-sessions", "-F", "#{session_name}").split()
    assert sorted(sessions) == ["cca-test", "cca-test-other"]


def test_tmux_create_file(tmux_env, monkeypatch, capsys):
    target = tmux_env / "remote" / "f.txt"
    content = b"a'b\"c\n$(id)\nno newline"
    assert cca(["--create-file", str(target), "server1"], monkeypatch, content) == 0
    assert target.read_bytes() == content


def test_tmux_create_file_too_large(tmux_env, monkeypatch, capsys):
    data = b"x" * (executor.TMUX_INPUT_MAX + 1)
    assert cca(["--create-file", "/tmp/x", "server1"], monkeypatch, data) == 2
    assert "cannot go through a tmux pane" in capsys.readouterr().err


def test_tmux_missing_session_setting(tmux_env, monkeypatch, capsys):
    project(tmux_env, run='transport = "tmux"\n')
    assert cca(["-t", "server1", "--", "id"], monkeypatch) == 2
    assert "run.tmux.session: required" in capsys.readouterr().err


def test_tmux_all(tmux_env, monkeypatch, capsys):
    assert cca(["--all", "--", "echo $CCA_TARGET"], monkeypatch) == 0
    out = capsys.readouterr().out
    assert out.index("admin@host1") < out.index("host2") < out.index("\nfail\n")
