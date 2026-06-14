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
      - name: local-qemu-ubuntu-dev-gui
        machine: local-qemu-medium
        os: ubuntu-26.04-arm64
        init: ssh-ubuntu-cloud-init
        bundles: [dev-ai]
        location: tokyo

      - name: vultr-windows-gaming
        machine: vultr-vcg-a40-2c
        os: windows-server-2025
        init: ssh-windows-powershell7
        bundles: [gaming-streaming]
        location: tokyo
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
    result = _run(script, env={**os.environ, "EVE_INSTANCE_NAME": "dev-a"})
    assert result.returncode != 0


def test_status_command_missing_eve_instance_name() -> None:
    env = {k: v for k, v in os.environ.items() if k != "EVE_INSTANCE_NAME"}
    result = _run("package-status-command", "docker", "echo hi", env=env)
    assert result.returncode != 0
    assert "EVE_INSTANCE_NAME is required" in result.stderr


def test_status_windows_missing_paths_exit_2() -> None:
    result = _run("package-status-windows", "docker", env={**os.environ, "EVE_INSTANCE_NAME": "dev-a"})
    assert result.returncode == 2
    assert "at least one path is required" in result.stderr


def test_verify_missing_instance_exit_2() -> None:
    result = _run("package-verify")
    assert result.returncode == 2
    assert "Usage:" in result.stderr


# --------------------- OS-family dispatch selection ------------------------ #
def test_provision_rejects_windows_profile(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision", "--profile", "vultr-windows-gaming", "--package", "steam",
        "--dry-run", env=catalog_env,
    )
    assert result.returncode == 2
    assert "granular package install is only implemented for ubuntu, got windows" in result.stderr


def test_provision_windows_rejects_ubuntu_profile(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "local-qemu-ubuntu-dev-gui",
        "--package", "docker", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 2
    assert "granular package install is only implemented for windows, got ubuntu" in result.stderr


# --------------------- package-provision dry-run seam ---------------------- #
def test_provision_dry_run_basic(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision", "--profile", "local-qemu-ubuntu-dev-gui",
        "--package", "docker", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-provision"
    assert payload["package"] == "docker"
    assert payload["os_family"] == "ubuntu"
    assert payload["dry_run"] is True
    assert payload["steps"] == ["base.sh", "timezone.sh", "provision/ubuntu/docker.sh"]


def test_provision_dry_run_dependency_chain(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision", "--profile", "local-qemu-ubuntu-dev-gui",
        "--package", "codex-cli", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "codex-cli"
    assert payload["steps"] == [
        "base.sh", "timezone.sh", "provision/ubuntu/dev-toolchain.sh",
        "provision/ubuntu/codex-cli.sh",
    ]
    assert payload["package_markers"] == ["dev-toolchain", "codex-cli"]


def test_provision_dry_run_profile_alias(catalog_env: dict[str, str]) -> None:
    """--instance and --profile are compatibility aliases."""
    result = _run(
        "package-provision", "--instance", "local-qemu-ubuntu-dev-gui",
        "--package", "docker", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["instance"] == "local-qemu-ubuntu-dev-gui"
    assert payload["profile"] == "local-qemu-ubuntu-dev-gui"


# ----------------- package-provision-windows dry-run seam ------------------ #
def test_provision_windows_dry_run_granular(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "vultr-windows-gaming",
        "--package", "steam", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-provision-windows"
    assert payload["package"] == "steam"
    assert payload["os_family"] == "windows"
    assert payload["steps"] == ["provision/windows/steam.ps1"]
    assert payload["state_files"] == []
    assert payload["fallback"] is False
    assert payload["dry_run"] is True


def test_provision_windows_dry_run_fallback(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "vultr-windows-gaming",
        "--package", "sunshine", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "sunshine"
    assert payload["steps"] == []
    assert payload["state_files"] == []
    assert payload["fallback"] is True


def test_provision_windows_dry_run_unmapped(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "vultr-windows-gaming",
        "--package", "docker", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["fallback"] is True


def test_provision_windows_dry_run_state_files(catalog_env: dict[str, str]) -> None:
    result = _run(
        "package-provision-windows", "--profile", "vultr-windows-gaming",
        "--package", "rustdesk", "--dry-run", env=catalog_env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "rustdesk"
    assert payload["steps"] == ["provision/windows/rustdesk.ps1"]
    assert payload["state_files"] == ["env.json"]
    assert payload["fallback"] is False


# --------------------- status-command contract ----------------------------- #
def test_status_command_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, _ = fake_ssh
    fake_installed = str(state_dir / "fake-ssh-installed")
    env = {**os.environ, "EVE_PACKAGE_STATUS_SSH": fake_installed, "EVE_INSTANCE_NAME": "dev-a"}
    result = _run("package-status-command", "docker", "ignored remote command", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-status"
    assert payload["package"] == "docker"
    assert payload["instance"] == "dev-a"
    assert payload["os_family"] == "ubuntu"
    assert payload["status"] == "installed"


def test_status_command_failed_status(fake_ssh: tuple[Path, Path]) -> None:
    """When the SSH helper exits non-zero, status becomes 'failed'."""
    state_dir, _ = fake_ssh
    fake_fail = state_dir / "fake-ssh-fail"
    fake_fail.write_text("#!/usr/bin/env sh\nset -eu\nexit 3\n")
    fake_fail.chmod(0o755)
    env = {**os.environ, "EVE_PACKAGE_STATUS_SSH": str(fake_fail), "EVE_INSTANCE_NAME": "dev-a"}
    result = _run("package-status-command", "docker", "echo hi", env=env)
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
        "package-status-windows", "steam", r"C:\Program Files (x86)\Steam\steam.exe",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-status"
    assert payload["package"] == "steam"
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
        "EVE_PACKAGE_STATUS_PROCESS": "rustdesk",
        "EVE_PACKAGE_STATUS_SERVICE_PATTERN": "rustdesk",
    }
    result = _run("package-status-windows", "rustdesk", r"C:\Program Files\RustDesk\rustdesk.exe", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "installed"
    assert payload["details"] == "running"


# --------------------- down-command contract ------------------------------- #
def test_down_command_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, fake_down = fake_ssh
    env = {**os.environ, "EVE_PACKAGE_DOWN_SSH": str(fake_down), "EVE_INSTANCE_NAME": "dev-a"}
    result = _run("package-down-command", "docker", "sudo apt-get remove -y docker-ce || true", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["package"] == "docker"
    assert payload["instance"] == "dev-a"
    assert payload["os_family"] == "ubuntu"
    assert payload["status"] == "removed"


def test_down_command_dry_run() -> None:
    env = {**os.environ, "EVE_INSTANCE_NAME": "dev-a", "EVE_PLUGIN_DRY_RUN": "1"}
    result = _run("package-down-command", "docker", "apt-get remove docker-ce", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["os_family"] == "ubuntu"
    assert payload["dry_run"] is True
    assert payload["command"] == "apt-get remove docker-ce"


# --------------------- down-windows contract ------------------------------- #
def test_down_windows_emits_contract(fake_ssh: tuple[Path, Path]) -> None:
    state_dir, fake_down = fake_ssh
    env = {**os.environ, "EVE_PACKAGE_DOWN_SSH": str(fake_down), "EVE_INSTANCE_NAME": "win-a"}
    result = _run("package-down-windows", "steam", "winget uninstall --id Valve.Steam --silent; exit 0", env=env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["package"] == "steam"
    assert payload["instance"] == "win-a"
    assert payload["os_family"] == "windows"
    assert payload["status"] == "removed"


def test_down_windows_dry_run() -> None:
    env = {**os.environ, "EVE_INSTANCE_NAME": "win-a", "EVE_PLUGIN_DRY_RUN": "1"}
    result = _run("package-down-windows", "steam", "winget uninstall Valve.Steam", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-down"
    assert payload["os_family"] == "windows"
    assert payload["dry_run"] is True
