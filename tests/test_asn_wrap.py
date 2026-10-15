"""Tests for the compact, agent-oriented asn-wrap output."""

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent.parent / "bin" / "asn-wrap"


def test_short_output_uses_yq_and_filters_asn_jq_noise(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_asn = fake_bin / "asn"
    fake_asn.write_text(
        """#!/bin/bash
cat >/dev/null  # consume stdin like the real asn, else asn-wrap's printf may hit SIGPIPE
printf '%s\\n' '{"target":"1.2.3.4","result":"ok","results":[{"ip":"1.2.3.4","org_name":"Example Org","routing":{"as_number":"64500"},"geolocation":{"cc":"CZ"},"type":{"is_dc":false,"is_proxy":true,"is_mobile":false},"reputation":{"status":"bad"},"reverse":"host.example"}]}'
printf '%s\\n' 'jq: parse error: Invalid numeric literal' >&2
printf '%s\\n' 'asn warning kept' >&2
""",
        encoding="utf-8",
    )
    fake_asn.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    result = subprocess.run(
        [str(SCRIPT), "-s", "1.2.3.4"], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0
    assert result.stdout == (
        "1.2.3.4|AS64500|CZ|d:false,p:true,m:false|r:bad|Example Org|host.example\n"
    )
    assert result.stderr == "asn warning kept\n"
