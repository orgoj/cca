"""cca server: fake ssh on PATH runs the remote command with fake remote tools only."""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from cca.cli import main
from cca.commands import server

SERVERS = (
    '[servers.server1]\nssh = "admin@host1"\n'
    '[servers.server2]\nssh = "fail"\n'
    '[servers.server3]\nssh = "host3"\n'
)
REMOTE_REAL = ("bash", "base64", "awk", "tr", "cat", "sleep")


def write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """PATH = only the fake ssh; the remote side sees only rbin/ (fake and a few real tools)."""
    for d in ("bin", "work", "rbin"):
        (tmp_path / d).mkdir()
    for tool in REMOTE_REAL:
        (tmp_path / "rbin" / tool).symlink_to(shutil.which(tool))
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    # without the sbin PATH extension: the test machine's own zpool/lxc-ls stay invisible
    monkeypatch.setattr(server, "PREFIX", "set -o pipefail; ")
    write_exe(
        tmp_path / "bin" / "ssh",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$2" >> "{tmp_path}/ssh.log"\n'
        '[ "$1" = "--" ] && [ $# -eq 3 ] || exit 99\n'
        'if [ "$2" = fail ]; then echo "ssh: connect to host fail: refused" >&2; exit 255; fi\n'
        f'exec /usr/bin/env -i PATH="{tmp_path}/rbin" /bin/sh -c "$3"\n',
    )
    tools = {
        "hostname": "echo h1",
        "date": "echo 2026-10-15T17:00:00+02:00",
        "uptime": "echo ' 17:00:00 up 3 days,  load average: 0.10, 0.20, 0.30'",
        "free": "printf 'total used\\nMem: 31Gi 4Gi\\nSwap: 2Gi 0B\\n'",
        "findmnt": "echo /",
        "df": 'echo "df $*"',
        "sed": "echo 'Test Linux 1'",
        "uname": "echo 'Linux 6.0'",
        "lscpu": "printf 'Architecture: x86_64\\nCPU(s): 8\\nModel name: Test CPU\\n'",
        "lsblk": 'echo "lsblk $*"',
        "ip": (
            'if [ "$1" = -br ]; then printf "lo UNKNOWN 127.0.0.1/8\\neth0 UP 192.0.2.1/24\\n'
            'wg0 UNKNOWN 10.1.0.1/24\\ndocker0 DOWN 172.17.0.1/16\\n"; '
            'else printf "1: lo inet 127.0.0.1/8 scope host lo\\n1: lo inet 10.9.0.1/32 scope '
            'global lo\\n1: lo inet6 ::1/128 scope host\\n"; fi'
        ),
        "lxc-ls": "echo never-without-sudo",
        "sudo": 'echo "sudo $*"',
        "ps": 'printf "  PID ELAPSED COMMAND\\n  42 01:00 /usr/bin/qemu-system-x86_64 -m 1G\\n"',
    }
    for name, body in tools.items():
        write_exe(tmp_path / "rbin" / name, f"#!/bin/sh\n{body}\n")
    return tmp_path


@pytest.fixture(autouse=True)
def only_ssh(monkeypatch):
    """Every child cca starts is an ssh argv: never tmux, never a local shell."""
    real = subprocess.Popen.__init__

    def guarded(self, args, *a, **kw):
        assert not kw.get("shell"), args
        assert isinstance(args, list) and os.path.basename(args[0]) == "ssh", args
        real(self, args, *a, **kw)

    monkeypatch.setattr(subprocess.Popen, "__init__", guarded)


def project(env: Path, extra: str = "") -> None:
    # run.transport = tmux: server commands still use ssh
    (env / "work" / ".cca.toml").write_text(
        f'schema_version = 1\n{SERVERS}[run]\ntransport = "tmux"\n{extra}'
    )


def ssh_calls(env: Path) -> list[str]:
    log = env / "ssh.log"
    return log.read_text().splitlines() if log.exists() else []


def test_hostname(env, capsys):
    project(env)
    assert main(["server", "hostname", "server1"]) == 0
    assert capsys.readouterr().out == '<hostname server="server1">h1</hostname>\n'
    assert ssh_calls(env) == ["admin@host1"]


def test_hostname_by_alias(env, capsys):
    servers = SERVERS.replace("[servers.server3]\n", '[servers.server3]\naliases = ["web"]\n')
    (env / "work" / ".cca.toml").write_text("schema_version = 1\n" + servers)
    assert main(["server", "hostname", "web"]) == 0
    assert capsys.readouterr().out == '<hostname server="server3">h1</hostname>\n'
    assert ssh_calls(env) == ["host3"]


def test_status(env, capsys):
    project(env)
    assert main(["server", "status", "server1"]) == 0
    out = capsys.readouterr().out
    assert re.fullmatch(
        r'<server-status server="server1">\n'
        r"<admin-time>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d</admin-time>\n"
        r"<server-time>2026-10-15T17:00:00\+02:00</server-time>\n"
        r"<load> 17:00:00 up 3 days,  load average: 0.10, 0.20, 0.30</load>\n"
        r"<memory>\ntotal used\nMem: 31Gi 4Gi\nSwap: 2Gi 0B\n</memory>\n"
        r"<storage>df -hT -t ext2 -t ext3 -t ext4 -t xfs</storage>\n"
        r"<zfs>ZFS not available</zfs>\n"
        r"</server-status>\n",
        out,
    ), out
    assert ssh_calls(env) == ["admin@host1"] * 5


def test_info(env, capsys):
    project(env, '[server_info]\nnet_iface_prefixes = ["eth", "wg"]\n')
    write_exe(env / "rbin" / "zpool", '#!/bin/sh\necho "zpool $*"\n')
    assert main(["server", "info", "server1"]) == 0
    assert capsys.readouterr().out == (
        '<server-info server="server1">\n'
        "<hostname>h1</hostname>\n"
        "<os>\nTest Linux 1\nLinux 6.0\n</os>\n"
        "<cpu>\nCPU(s): 8\nModel name: Test CPU\n</cpu>\n"
        "<memory>\nMem: 31Gi\nSwap: 2Gi\n</memory>\n"
        "<disks>lsblk -d -e 1,7,11 -o NAME,SIZE,ROTA,MODEL</disks>\n"
        "<zfs>zpool status</zfs>\n"
        "<network>\neth0 UP 192.0.2.1/24\nwg0 UNKNOWN 10.1.0.1/24\n</network>\n"
        "<loopback>10.9.0.1/32</loopback>\n"
        "<docker>Docker not available</docker>\n"
        "<swarm>Docker not available</swarm>\n"
        "<lxc>sudo -n lxc-ls -f</lxc>\n"
        "<qemu>  42 01:00 /usr/bin/qemu-system-x86_64 -m 1G</qemu>\n"
        "</server-info>\n"
    )


def test_info_empty_and_docker(env, capsys):
    project(env)  # default prefixes en|eth
    write_exe(env / "rbin" / "ip", "#!/bin/sh\necho 'lo UNKNOWN 127.0.0.1/8'\n")
    write_exe(env / "rbin" / "ps", "#!/bin/sh\necho '  PID ELAPSED COMMAND'\n")
    write_exe(
        env / "rbin" / "docker",
        "#!/bin/sh\n"
        'case "$1" in ps) echo "docker $*";; info) echo true;; service) echo "svc ls";; esac\n',
    )
    assert main(["server", "info", "server1"]) == 0
    out = capsys.readouterr().out
    assert "<network>no interfaces matching en|eth</network>\n" in out
    assert "<loopback>no loopback aliases</loopback>\n" in out
    assert "<qemu>no QEMU processes</qemu>\n" in out
    assert "<docker>docker ps --format table {{.Names}}\t{{.Image}}\t{{.Status}}</docker>" in out
    assert "<swarm>svc ls</swarm>\n" in out


def test_swarm_worker_and_docker_failure(env, capsys):
    project(env)
    write_exe(env / "rbin" / "docker", '#!/bin/sh\n[ "$1" = info ] && echo false\nexit 0\n')
    assert main(["server", "info", "server1"]) == 0
    assert "<swarm>not a Swarm manager</swarm>\n" in capsys.readouterr().out
    write_exe(env / "rbin" / "docker", "#!/bin/sh\necho 'permission denied' >&2\nexit 1\n")
    assert main(["server", "info", "server1"]) == 0
    out = capsys.readouterr().out
    assert '<docker exit="1">permission denied</docker>\n' in out
    assert '<swarm exit="1">permission denied</swarm>\n' in out


def test_failing_section_continues(env, capsys):
    project(env)
    write_exe(env / "rbin" / "lscpu", "#!/bin/sh\necho 'lscpu: broken' >&2\nexit 3\n")
    write_exe(env / "rbin" / "ip", "#!/bin/sh\nexit 4\n")
    assert main(["server", "info", "server1"]) == 0
    out = capsys.readouterr().out
    assert '<cpu exit="3">lscpu: broken</cpu>\n' in out  # pipefail: lscpu's status
    assert '<network exit="4"></network>\n' in out  # not "no interfaces matching"
    assert '<loopback exit="4"></loopback>\n' in out
    assert out.endswith("</server-info>\n")


def test_ssh_failure_stops(env, capsys):
    project(env)
    assert main(["server", "status", "server2"]) == 255
    captured = capsys.readouterr()
    assert captured.out == (
        '<server-status server="server2">\n'
        + re.search(r"<admin-time>.*</admin-time>\n", captured.out).group(0)
        + '<server-time exit="255">ssh: connect to host fail: refused</server-time>\n'
        "</server-status>\n"
    )
    assert "server2: ssh failed" in captured.err
    assert ssh_calls(env) == ["fail"]


def test_all_stops_on_first_failure(env, capsys):
    project(env)
    assert main(["server", "hostname", "--all"]) == 255
    assert capsys.readouterr().out == (
        '<hostname server="server1">h1</hostname>\n'
        '<hostname server="server2" exit="255">ssh: connect to host fail: refused</hostname>\n'
    )
    assert ssh_calls(env) == ["admin@host1", "fail"]


def test_all_config_order(env, capsys):
    (env / "work" / ".cca.toml").write_text(
        'schema_version = 1\n[servers.b]\nssh = "hb"\n[servers.a]\nssh = "ha"\n'
    )
    assert main(["server", "hostname", "--all"]) == 0
    assert capsys.readouterr().out == (
        '<hostname server="b">h1</hostname>\n<hostname server="a">h1</hostname>\n'
    )


def test_timeout_is_total(env, capsys):
    project(env)
    write_exe(env / "rbin" / "uptime", "#!/bin/sh\necho partial\nexec sleep 10\n")
    assert main(["server", "status", "--timeout", "1", "server1"]) == 124
    captured = capsys.readouterr()
    assert '<load exit="timeout">partial</load>\n</server-status>\n' in captured.out
    assert "<memory>" not in captured.out
    assert "section load did not finish in time" in captured.err
    assert len(ssh_calls(env)) == 2


def test_log_line_per_section(env):
    project(env, '[run.log]\noperator = "tester"\n')
    (env / "work" / "logs").mkdir()
    assert main(["server", "hostname", "server1"]) == 0
    lines = [
        line
        for f in sorted((env / "work" / "logs").iterdir())
        for line in f.read_text().splitlines()
    ]
    assert len(lines) == 1 and "server1" in lines[0] and "hostname" in lines[0]


@pytest.mark.parametrize(
    "argv, message",
    [
        (["status"], "give either SERVER or --all"),
        (["status", "--all", "server1"], "give either SERVER or --all"),
        (["status", "--timeout", "0", "server1"], "--timeout must be an integer 1-86400"),
        (["status", "nope"], "unknown server 'nope'"),
    ],
)
def test_usage_errors(env, capsys, argv, message):
    project(env)
    assert main(["server", *argv]) == 2
    assert message in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_unknown_section(env, capsys):
    project(env)
    with pytest.raises(SystemExit) as e:
        main(["server", "bogus", "server1"])
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert ssh_calls(env) == []


def test_all_without_servers(env, capsys):
    (env / "work" / ".cca.toml").write_text("schema_version = 1\n")
    assert main(["server", "info", "--all"]) == 2
    assert "no [servers] configured" in capsys.readouterr().err


def test_help(capsys):
    with pytest.raises(SystemExit):
        main(["server", "--help"])
    out = capsys.readouterr().out
    assert "{hostname,status,info}" in out and "exit status" in out
