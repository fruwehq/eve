"""Behavior parity for the ssh-wait / wait-for-provision pollers (Phase 2 port).

Covers the testable seams without a live instance / SSH:

- ``ssh-wait`` / ``wait-for-provision``: usage / missing-arg exit 2, and the
  max-wait=0 timeout path (loop never runs → exit 1) which exercises arg +
  interval parsing and profile resolution without contacting a VM.
- ``wait-for-provision``: the status-file probe dispatch (DONE / FAILED /
  MALFORMED) via the ``EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT`` seam, plus the
  NOT_PRESENT → log-probe DONE fallback — all with tiny max-wait / poll
  intervals so nothing sleeps.
- ``eve_sdk.provision_pollers``: probe-script builder shape, ``clean_step``,
  ``parse_probe_result``, and ``classify_status_json`` (DONE / RUNNING / FAILED
  / NOT_PRESENT / MALFORMED incl. schema violations) as pure functions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from eve_sdk.provision_pollers import (  # noqa: E402
    build_log_probe,
    build_status_probe,
    classify_status_json,
    clean_step,
    parse_probe_result,
)

_CATALOG = dedent(
    """\
    profiles:
      - name: poll-ubuntu
        machine: mock-small
        os: mockos-1.0-arm64
        init: ssh-mockos-cloud-init
        bundles: []
        location: mock-tokyo
      - name: poll-windows
        machine: mock-gpu
        os: mockwin-1.0
        init: ssh-mockwin-powershell
        bundles: []
        location: mock-tokyo
    """
)


@pytest.fixture()
def catalog_env(tmp_path: Path) -> dict[str, str]:
    """Env with a temp catalog exposing ubuntu/windows profiles for resolution."""
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAA_test test@test\n")
    catalog = tmp_path / "poll-catalog.local.yaml"
    catalog.write_text(_CATALOG)
    env = {
        **os.environ,
        "SSH_PUBLIC_KEY_FILE": str(key),
        "EVE_CATALOG_LOCAL": str(catalog),
        "EVE_INSTANCE_WORKDIR": str(tmp_path / "work"),
        "EVE_STATE_DIR": str(tmp_path / "state"),
    }
    env.pop("INSTANCE", None)
    return env


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


def _probe_stub(tmp_path: Path, status_response: str, log_response: str = "") -> Path:
    """Write a tiny probe-stub script (the EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT seam).

    arg1 = os_family, arg2 = "status" (status probe) or an integer (log probe).
    Responses are written to files and ``cat``-ed verbatim so tab/newline bytes
    survive byte-exact (matching what the real remote printf would emit).
    """
    status_file = tmp_path / "status.resp"
    status_file.write_text(status_response, encoding="utf-8")
    log_file = tmp_path / "log.resp"
    log_file.write_text(log_response, encoding="utf-8")
    stub = tmp_path / "probe-stub.sh"
    stub.write_text(
        "#!/usr/bin/env sh\n"
        f'if [ "$2" = "status" ]; then cat "{status_file}"; '
        f'else cat "{log_file}"; fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


# ============================ usage / missing arg ========================== #
def test_ssh_wait_missing_arg(catalog_env: dict[str, str]) -> None:
    result = _run("ssh-wait", env=catalog_env)
    assert result.returncode == 2
    assert "Usage: scripts/ssh-wait <instance> [max-wait-seconds]" in result.stderr
    assert result.stdout == ""


def test_wait_for_provision_missing_arg(catalog_env: dict[str, str]) -> None:
    result = _run("wait-for-provision", env=catalog_env)
    assert result.returncode == 2
    assert "Usage: scripts/wait-for-provision <instance> [max-wait-seconds]" in result.stderr
    assert result.stdout == ""


# ============================ timeout paths (max-wait 0) ================== #
def test_ssh_wait_timeout_exits_1(catalog_env: dict[str, str]) -> None:
    # max-wait=0: loop condition false immediately → "did not become ready".
    result = _run("ssh-wait", "poll-ubuntu", "0", env=catalog_env)
    assert result.returncode == 1
    assert "SSH did not become ready in time for profile poll-ubuntu (0s)" in result.stderr


def test_wait_for_provision_timeout_exits_1(catalog_env: dict[str, str]) -> None:
    # max-wait=0: loop never runs → "did not finish". profile-resolve still runs.
    result = _run("wait-for-provision", "poll-ubuntu", "0", env=catalog_env)
    assert result.returncode == 1
    assert "Provisioning did not finish in time for profile poll-ubuntu (0s)" in result.stderr
    assert "Last seen step: (none yet)" in result.stderr


# ====================== wait-for-provision probe dispatch ================== #
def test_wait_for_provision_status_done_exits_0(
    catalog_env: dict[str, str], tmp_path: Path,
) -> None:
    done_json = json.dumps({
        "api_version": 1, "os_family": "ubuntu", "started_at": None, "status": "done",
        "steps": [{"step": "finish.sh", "phase": "succeeded",
                   "started_at": None, "ended_at": None, "exit_code": 0}],
    })
    stub = _probe_stub(tmp_path, status_response=done_json)
    env = {**catalog_env,
           "EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT": str(stub),
           "EVE_PROVISION_WAIT_POLL_INTERVAL": "0"}
    result = _run("wait-for-provision", "poll-ubuntu", "2", env=env)
    assert result.returncode == 0
    assert "Provisioning complete for profile poll-ubuntu (0s, 1/1, last step: finish.sh)" in result.stdout


def test_wait_for_provision_status_failed_exits_1(
    catalog_env: dict[str, str], tmp_path: Path,
) -> None:
    failed_json = json.dumps({
        "api_version": 1, "os_family": "ubuntu", "started_at": None, "status": "failed",
        "steps": [{"step": "broken.sh", "phase": "failed",
                   "started_at": None, "ended_at": None, "exit_code": 1}],
    })
    stub = _probe_stub(tmp_path, status_response=failed_json)
    env = {**catalog_env,
           "EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT": str(stub),
           "EVE_PROVISION_WAIT_POLL_INTERVAL": "0"}
    result = _run("wait-for-provision", "poll-ubuntu", "2", env=env)
    assert result.returncode == 1
    assert "Provisioning failed for profile poll-ubuntu (0s, 0/1)" in result.stderr
    assert "Failed step: broken.sh" in result.stderr


def test_wait_for_provision_status_malformed_exits_1(
    catalog_env: dict[str, str], tmp_path: Path,
) -> None:
    stub = _probe_stub(tmp_path, status_response="STATUS_FILE\tMALFORMED\n")
    env = {**catalog_env,
           "EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT": str(stub),
           "EVE_PROVISION_WAIT_POLL_INTERVAL": "0"}
    result = _run("wait-for-provision", "poll-ubuntu", "2", env=env)
    assert result.returncode == 1
    assert "Provision status file exists but is malformed. Refusing to silently ignore." in result.stderr
    assert "Run: scripts/instance-ssh poll-ubuntu --" in result.stderr


def test_wait_for_provision_log_probe_done_fallback(
    catalog_env: dict[str, str], tmp_path: Path,
) -> None:
    # Status probe reports ABSENT (NOT_PRESENT) → falls through to log probe,
    # which reports STATE DONE → exits 0 via the log-probe path.
    log_resp = "STATE\tDONE\nLINES\t1\nLAST\tRunning step finish.sh\n__EVE_LOG_BEGIN__\n"
    stub = _probe_stub(tmp_path, status_response="STATUS_FILE\tABSENT\n", log_response=log_resp)
    env = {**catalog_env,
           "EVE_WAIT_FOR_PROVISION_PROBE_SCRIPT": str(stub),
           "EVE_PROVISION_WAIT_POLL_INTERVAL": "0"}
    result = _run("wait-for-provision", "poll-ubuntu", "2", env=env)
    assert result.returncode == 0
    assert "Provisioning complete for profile poll-ubuntu (0s, last step: finish.sh)" in result.stdout


# ============================ probe-script builders ======================= #
def test_build_status_probe_ubuntu_shape() -> None:
    probe = build_status_probe("ubuntu")
    assert probe.startswith('sf="$HOME/provision/state/provision-status.json"')
    assert "printf 'STATUS_FILE\\tABSENT\\n'" in probe
    assert "printf 'STATUS_FILE\\tMALFORMED\\n'" in probe
    assert probe.endswith('cat "$sf"\n')


def test_build_status_probe_windows_shape() -> None:
    probe = build_status_probe("windows")
    assert 'C:\\Users\\Administrator\\provision\\state\\provision-status.json' in probe
    assert '"STATUS_FILE`tABSENT"' in probe
    assert probe.endswith("Get-Content $sf\n")


def test_build_status_probe_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown os_family: macos"):
        build_status_probe("macos")


def test_build_log_probe_ubuntu_offset_header() -> None:
    probe = build_log_probe("ubuntu", 7)
    assert probe.startswith("offset=7\n")
    assert 'log="$HOME/provision/logs/provision.log"' in probe
    assert "printf 'STATE\\t%s\\n'" in probe
    assert "/Provisioning complete\\./" in probe


def test_build_log_probe_windows_offset_header() -> None:
    probe = build_log_probe("windows", 3)
    assert probe.startswith("$offset = 3\n")
    assert '$log = "C:\\Users\\Administrator\\provision\\logs\\provision.log"' in probe
    assert '"STATE${tab}$state"' in probe


def test_build_log_probe_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown os_family: freebsd"):
        build_log_probe("freebsd", 0)


# ============================ clean_step ================================== #
@pytest.mark.parametrize(
    "line,expected",
    [
        ("2024-01-01 12:00:00 Running step [11/12] rustdesk.sh", "[11/12] rustdesk.sh"),
        ("Running step base.sh", "base.sh"),
        ("[3/4] mock-app.sh", "[3/4] mock-app.sh"),
        ("", ""),
        ("2024-06-15 01:02:03 ERROR: something failed", "ERROR: something failed"),
    ],
)
def test_clean_step(line: str, expected: str) -> None:
    assert clean_step(line) == expected


# ============================ parse_probe_result ========================== #
def test_parse_probe_result_done_with_log() -> None:
    raw = (
        "STATE\tDONE\n"
        "LINES\t3\n"
        "LAST\tRunning step finish.sh\n"
        "__EVE_LOG_BEGIN__\n"
        "line one\n"
        "line two\n"
    )
    parsed = parse_probe_result(raw)
    assert parsed.state == "DONE"
    assert parsed.line_count == 3
    assert parsed.step_line == "Running step finish.sh"
    assert parsed.new_log == "line one\nline two"


def test_parse_probe_result_missing_log_file() -> None:
    raw = "STATE\tMISSING\nLINES\t0\nLAST\t\n__EVE_LOG_BEGIN__\n"
    parsed = parse_probe_result(raw)
    assert parsed.state == "MISSING"
    assert parsed.line_count == 0
    assert parsed.step_line == ""
    assert parsed.new_log == ""


def test_parse_probe_result_non_integer_lines() -> None:
    raw = "STATE\tRUNNING\nLINES\tnot-a-number\nLAST\tfoo\n__EVE_LOG_BEGIN__\n"
    parsed = parse_probe_result(raw)
    assert parsed.line_count is None


# ============================ classify_status_json ======================== #
def _status_json(**overrides: object) -> str:
    base: dict[str, object] = {
        "api_version": 1,
        "os_family": "ubuntu",
        "started_at": None,
        "status": "running",
        "steps": [],
    }
    base.update(overrides)
    return json.dumps(base)


def _step(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "step": "base.sh", "phase": "succeeded",
        "started_at": None, "ended_at": None, "exit_code": 0,
    }
    base.update(overrides)
    return base


def test_classify_absent_header() -> None:
    assert classify_status_json("STATUS_FILE\tABSENT\n") == "NOT_PRESENT"


def test_classify_malformed_header() -> None:
    assert classify_status_json("STATUS_FILE\tMALFORMED\n") == "MALFORMED"


def test_classify_invalid_json() -> None:
    assert classify_status_json("not json at all") == "MALFORMED"


def test_classify_empty() -> None:
    assert classify_status_json("") == "MALFORMED"


def test_classify_done() -> None:
    raw = _status_json(status="done", steps=[_step(step="finish.sh")])
    assert classify_status_json(raw) == "DONE\tfinish.sh\t1/1"


def test_classify_running_progress() -> None:
    raw = _status_json(status="running", steps=[
        _step(step="base.sh", phase="succeeded"),
        _step(step="mock-app.sh", phase="running", exit_code=None),
    ])
    assert classify_status_json(raw) == "RUNNING\tmock-app.sh\t1/2"


def test_classify_failed_step() -> None:
    raw = _status_json(status="failed", steps=[
        _step(step="base.sh", phase="succeeded"),
        _step(step="rustdesk.sh", phase="failed", exit_code=1),
    ])
    assert classify_status_json(raw) == "FAILED\trustdesk.sh\t1/2"


def test_classify_done_empty_steps() -> None:
    raw = _status_json(status="done", steps=[])
    assert classify_status_json(raw) == "DONE\t\t0/0"


@pytest.mark.parametrize(
    "bad",
    [
        _status_json(api_version=2),                       # wrong api_version
        _status_json(api_version=True),                    # bool api_version (jq true != 1)
        _status_json(os_family="macos"),                   # bad os_family
        _status_json(status="paused"),                     # bad status
        _status_json(steps="not-an-array"),                # steps not array
        _status_json(steps=[_step(step="")]),              # empty step name
        _status_json(steps=[_step(step=123)]),             # non-string step name
        _status_json(steps=[_step(phase="done")]),         # bad phase
        _status_json(steps=[{"step": "x", "phase": "pending"}]),  # missing keys
        _status_json(steps=[_step(exit_code=1.5)]),        # non-integer float
        _status_json(steps=[_step(exit_code=True)]),       # bool exit_code
        _status_json(steps=[_step(started_at=123)]),       # non-string/null started_at
    ],
)
def test_classify_schema_violations(bad: str) -> None:
    assert classify_status_json(bad) == "MALFORMED"


def test_classify_exit_code_float_integer_passes() -> None:
    # jq ``. == floor`` accepts integer-valued floats (5.0 == floor).
    raw = _status_json(status="done", steps=[_step(step="ok.sh", exit_code=5.0)])
    assert classify_status_json(raw) == "DONE\tok.sh\t1/1"
