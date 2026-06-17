"""Behavior parity for the package-* dispatchers (Phase 2 bash->Python port).

Drives the seven ported scripts as subprocesses and asserts the CLI contract:
usage/missing-arg handling, OS-family dispatch selection, dry-run/validation
seams (dependency chain resolution, fallback), and the status/down JSON
contracts via fake SSH helpers. No real instance or SSH connection is required.
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

_CATALOG = dedent(
    """\
    profiles:
      - name: mock-cloud-ubuntu-dev-gui
        machine: mock-small
        os: mockos-1.0-arm64
        init: ssh-mockos-cloud-init
        bundles: [mock-dev]
        location: mock-tokyo

      - name: mock-win-gaming
        machine: mock-small
        os: mockwin-1.0
        init: ssh-mockwin-powershell
        bundles: [mock-gaming]
        location: mock-tokyo
    """
)


@pytest.fixture()
def catalog_env(tmp_path: Path) -> dict[str, str]:
    """Env with a temp local catalog exposing ubuntu + windows profiles."""
    catalog = tmp_path / "catalog.local.yaml"
    catalog.write_text(_CATALOG)
    return {**os.environ, "EVE_CATALOG_LOCAL": str(catalog)}


@pytest.fixture()
def fake_ssh(tmp_path: Path) -> tuple[Path, Path]:
    """Create fake SSH helpers: one prints 'installed', one captures args."""
    state_dir = tmp_path / "ssh-state"
    state_dir.mkdir()
    fake_installed = state_dir / "fake-ssh-installed"
    fake_installed.write_text("#!/usr/bin/env sh\nset -eu\nprintf 'installed\\n'\n")
    fake_installed.chmod(0o755)
    fake_capture = state_dir / "fake-ssh-capture"
    fake_capture.write_text(
        "#!/usr/bin/env sh\nset -eu\n"
        'printf "%s\\n" "$*" >"${EVE_FAKE_SSH_ARGS:?}"\n'
        "printf '#< CLIXML\\n'\nprintf 'installed\\n'\n"
    )
    fake_capture.chmod(0o755)
    fake_running = state_dir / "fake-ssh-running"
    fake_running.write_text("#!/usr/bin/env sh\nset -eu\nprintf 'running\\n'\n")
    fake_running.chmod(0o755)
    fake_down = state_dir / "fake-ssh-down"
    fake_down.write_text("#!/usr/bin/env sh\nset -eu\nexit 0\n")
    fake_down.chmod(0o755)
    return state_dir, fake_down


def _run(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# --------------------------- usage / missing arg --------------------------- #
@pytest.mark.parametrize("script,usage_prefix", [
    ("package-provision", "Usage:\n  scripts/package-provision"),
    ("package-provision-windows", "Usage:\n  scripts/package-provision-windows"),
])
def test_provision_missing_args_exit_2(script: str, usage_prefix: str) -> None:
    result = _run(script)
    assert result.returncode == 2
    assert usage_prefix in result.stderr


def test_provision_missing_package_exit_2() -> None:
    result = _run("package-provision", "--instance", "foo")
    assert result.returncode == 2
    assert "Usage:" in result.stderr


@pytest.mark.parametrize("script", ["package-status-command", "package-down-command"])
def test_command_missing_args_exit_nonzero(script: str) -> None:
    result = _run(script, env={**os.environ, "EVE_INSTANCE_NAME": "mock-dev-a"})
    assert result.returncode != 0


def test_status_command_missing_eve_instance_name() -> None:
    env = {k: v for k, v in os.environ.items() if k != "EVE_INSTANCE_NAME"}
    result = _run("package-status-command", "mock-app", "echo hi", env=env)
    assert result.returncode != 0
    assert "EVE_INSTANCE_NAME is required" in result.stderr


def test_status_windows_missing_paths_exit_2() -> None:
    result = _run("package-status-windows", "mock-app", env={**os.environ, "EVE_INSTANCE_NAME": "mock-dev-a"})
    assert result.returncode == 2
    assert "at least one path is required" in result.stderr


def test_verify_missing_instance_exit_2() -> None:
    result = _run("package-verify")
    assert result.returncode == 2
    assert "Usage:" in result.stderr


# --------------------- OS-family dispatch selection ------------------------ #
def test_provision_rejects_windows_profile(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision", "--profile", "mock-win-gaming", "--package", "mock-app",
        "--dry-run", env=catalog_env,
    )
    assert result.returncode == 2
    assert "granular package install is only implemented for ubuntu, got windows" in result.stderr


def test_provision_windows_rejects_ubuntu_profile(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "mock-cloud-ubuntu-dev-gui",
        "--package", "mock-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 2
    assert "granular package install is only implemented for windows, got ubuntu" in result.stderr


# --------------------- package-provision dry-run seam ---------------------- #
def test_provision_dry_run_basic(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision", "--profile", "mock-cloud-ubuntu-dev-gui",
        "--package", "mock-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-provision"
    assert payload["package"] == "mock-app"
    assert payload["os_family"] == "ubuntu"
    assert payload["dry_run"] is True
    assert payload["steps"] == ["base.sh", "provision/ubuntu/mock-app.sh"]


def test_provision_dry_run_dependency_chain(catalog_env: dict[str, str]) -> None:
    # mock-tool depends_on mock-app: the chain expands deps-first and unions
    # each plugin's install.ubuntu.steps with stable first-occurrence dedup.
    result = _run(
        "package-provision", "--profile", "mock-cloud-ubuntu-dev-gui",
        "--package", "mock-tool", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "mock-tool"
    assert payload["steps"] == [
        "base.sh", "provision/ubuntu/mock-app.sh",
        "provision/ubuntu/mock-tool.sh",
    ]
    assert payload["package_markers"] == ["mock-app", "mock-tool"]


def test_provision_dry_run_profile_alias(catalog_env: dict[str, str]) -> None:
    """--instance and --profile are compatibility aliases."""
    result = _run(
        "package-provision", "--instance", "mock-cloud-ubuntu-dev-gui",
        "--package", "mock-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["instance"] == "mock-cloud-ubuntu-dev-gui"
    assert payload["profile"] == "mock-cloud-ubuntu-dev-gui"


# ----------------- package-provision-windows dry-run seam ------------------ #
def test_provision_windows_dry_run_granular(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "mock-win-gaming",
        "--package", "mock-win-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-provision-windows"
    assert payload["package"] == "mock-win-app"
    assert payload["os_family"] == "windows"
    assert payload["steps"] == ["provision/windows/mock-win-app.ps1"]
    assert payload["state_files"] == []
    assert payload["fallback"] is False
    assert payload["dry_run"] is True


def test_provision_windows_dry_run_fallback(catalog_env: dict[str, str]) -> None:
    # mock-app has no windows install mapping -> full-provision fallback.
    result = _run(
        "package-provision-windows", "--profile", "mock-win-gaming",
        "--package", "mock-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "mock-app"
    assert payload["steps"] == []
    assert payload["state_files"] == []
    assert payload["fallback"] is True


def test_provision_windows_dry_run_unmapped(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "mock-win-gaming",
        "--package", "mock-app", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["fallback"] is True


def test_provision_windows_dry_run_state_files(catalog_env: dict[str, str]) -> None:
    # mock-win-state declares install.windows.state_files.
    result = _run(
        "package-provision-windows", "--profile", "mock-win-gaming",
        "--package", "mock-win-state", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "mock-win-state"
    assert payload["steps"] == ["provision/windows/mock-win-state.ps1"]
    assert payload["state_files"] == ["env.json"]
    assert payload["fallback"] is False


# --------------------- status-command contract ----------------------------- #
def test_status_command_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, _ = fake_ssh
    fake_installed = str(state_dir / "fake-ssh-installed")
    env = {**os.environ, "EVE_PACKAGE_STATUS_SSH": fake_installed, "EVE_INSTANCE_NAME": "mock-dev-a"}
    result = _run("package-status-command", "mock-app", "ignored remote command", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-status"
    assert payload["package"] == "mock-app"
    assert payload["instance"] == "mock-dev-a"
    assert payload["os_family"] == "ubuntu"
    assert payload["status"] == "installed"


def test_status_command_failed_status(fake_ssh: tuple[Path, Path]) -> None:
    """When the SSH helper exits non-zero, status becomes 'failed'."""
    state_dir, _ = fake_ssh
    fake_fail = state_dir / "fake-ssh-fail"
    fake_fail.write_text("#!/usr/bin/env sh\nset -eu\nexit 3\n")
    fake_fail.chmod(0o755)
    env = {**os.environ, "EVE_PACKAGE_STATUS_SSH": str(fake_fail), "EVE_INSTANCE_NAME": "mock-dev-a"}
    result = _run("package-status-command", "mock-app", "echo hi", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"


# --------------------- status-windows contract ----------------------------- #
def test_status_windows_emits_contract(fake_ssh: tuple[Path, Path], tmp_path: Path) -> None:
    state_dir, _ = fake_ssh
    fake_capture = str(state_dir / "fake-ssh-capture")
    args_file = str(tmp_path / "ssh-args.txt")
    env = {
        **os.environ,
        "EVE_PACKAGE_STATUS_SSH": fake_capture,
        "EVE_FAKE_SSH_ARGS": args_file,
        "EVE_INSTANCE_NAME": "win-a",
    }
    result = _run(
        "package-status-windows", "mock-app", r"C:\Program Files (x86)\Steam\steam.exe",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-status"
    assert payload["package"] == "mock-app"
    assert payload["instance"] == "win-a"
    assert payload["os_family"] == "windows"
    assert payload["status"] == "installed"
    assert payload["details"] == "installed"
    # The PowerShell script must be encoded, not passed as raw text.
    raw_args = Path(args_file).read_text()
    assert "-EncodedCommand" in raw_args
    assert "$paths" not in raw_args


def test_status_windows_running_normalizes_to_installed(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, _ = fake_ssh
    fake_running = str(state_dir / "fake-ssh-running")
    env = {
        **os.environ,
        "EVE_PACKAGE_STATUS_SSH": fake_running,
        "EVE_INSTANCE_NAME": "win-a",
        "EVE_PACKAGE_STATUS_PROCESS": "mock-app",
        "EVE_PACKAGE_STATUS_SERVICE_PATTERN": "mock-app",
    }
    result = _run("package-status-windows", "mock-app", r"C:\Program Files\RustDesk\rustdesk.exe", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "installed"
    assert payload["details"] == "running"


# --------------------- down-command contract ------------------------------- #
def test_down_command_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, fake_down = fake_ssh
    env = {**os.environ, "EVE_PACKAGE_DOWN_SSH": str(fake_down), "EVE_INSTANCE_NAME": "mock-dev-a"}
    result = _run("package-down-command", "mock-app", "sudo apt-get remove -y mock-app-ce || true", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["package"] == "mock-app"
    assert payload["instance"] == "mock-dev-a"
    assert payload["os_family"] == "ubuntu"
    assert payload["status"] == "removed"


def test_down_command_dry_run() -> None:
    env = {**os.environ, "EVE_INSTANCE_NAME": "mock-dev-a", "EVE_PLUGIN_DRY_RUN": "1"}
    result = _run("package-down-command", "mock-app", "apt-get remove mock-app-ce", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["os_family"] == "ubuntu"
    assert payload["dry_run"] is True
    assert payload["command"] == "apt-get remove mock-app-ce"


# --------------------- down-windows contract ------------------------------- #
def test_down_windows_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, fake_down = fake_ssh
    env = {**os.environ, "EVE_PACKAGE_DOWN_SSH": str(fake_down), "EVE_INSTANCE_NAME": "win-a"}
    result = _run("package-down-windows", "mock-app", "winget uninstall --id Valve.Steam --silent; exit 0", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["package"] == "mock-app"
    assert payload["instance"] == "win-a"
    assert payload["os_family"] == "windows"
    assert payload["status"] == "removed"


def test_down_windows_dry_run() -> None:
    env = {**os.environ, "EVE_INSTANCE_NAME": "win-a", "EVE_PLUGIN_DRY_RUN": "1"}
    result = _run("package-down-windows", "mock-app", "winget uninstall Valve.Steam", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["os_family"] == "windows"
    assert payload["dry_run"] is True
