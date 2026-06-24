"""Behavior parity for profile-resolve and provision (Phase 2 bash->Python port).

Drives ``scripts/profile-resolve`` and ``scripts/provision`` as subprocesses
and asserts the CLI contract:

- profile-resolve: ``--emit env`` output is byte-identical for known profiles;
  each ``--emit`` mode (env/json/vagrant); usage/missing-arg exits 2; bad
  profile exits 5 (jq ``error()`` contract preserved).
- provision: usage/missing-arg exits 2; unknown os_family exits 2; OS dir
  validation exits 2. No live SSH/instances/cloud required — the dispatch
  seams that need a running instance are exercised only up to the point where
  external connectivity would be required.
"""

from __future__ import annotations

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
      - name: pr-ubuntu-qemu
        machine: mock-vm
        os: mockos-1.0-arm64
        init: ssh-mockos-cloud-init
        bundles: [mock-dev]
        location: mock-tokyo
      - name: pr-windows-aws
        machine: mock-gpu
        os: mockwin-1.0
        init: ssh-mockwin-powershell
        bundles: [mock-gaming]
        location: mock-tokyo
    """
)

# Exact KEY=value lines for the ubuntu-qemu profile, resolved against the
# hermetic mock fixtures (machine mock-vm -> provider mock-local, engine qemu).
# VM_USER_NAME is unset, so the access users resolve through the rule's static
# `value`/`fallback` (mock-local ubuntu -> "vagrant") via the same chain
# instance-resolve uses. VM_USER_NAME itself stays env-sourced (blank). This is
# the deterministic golden for the decoupled, self-contained test suite.
_EXPECTED_ENV_LINES = [
    "ACCESS_BOOTSTRAP_USER=vagrant",
    "ACCESS_HUMAN_USER=vagrant",
    "ACCESS_PROVISION_USER=vagrant",
    "PROFILE_NAME=pr-ubuntu-qemu",
    "ENGINE=qemu",
    "PROVIDER=mock-local",
    "STACK_TAGS=mock-local",
    "LOCATION_NAME=mock-tokyo",
    "OS_ID=mockos-1.0-arm64",
    "OS_FAMILY=ubuntu",
    "INIT_ID=ssh-mockos-cloud-init",
    "BUNDLE_PACKAGES=mock-app",
    "VM_MEMORY_MB=4096",
    "VM_CPU_CORES=2",
    "VM_CPU_MODE=",
    "VM_VCPUS=1",
    "VM_AUTOSTART=true",
    "VM_STATE=STOPPED",
    "VM_NIC_ATTACH=br0",
    "VM_DISK_GB=20",
    "VM_POOL=main",
    "VM_PLAN=",
    "VM_MACHINE_TYPE=",
    "VM_DISK_TYPE=",
    "VM_INSTANCE_TYPE=",
    "VM_ROOT_VOLUME_TYPE=",
    "VM_USE_SPOT=",
    "LOCATION_REGION=",
    "LOCATION_AVAILABILITY_ZONE=",
    "LOCATION_ZONE=",
    "SSH_USER=vagrant",
    "HUMAN_USER_NAME=vagrant",
    "PROVISION_USER_NAME=vagrant",
    "VM_USER_NAME=",
    # Provider-specific env now emitted generically after the core keys, sorted
    # by name (from each provider manifest's env_emission) — §15.5c. The mock
    # provider declares only MOCK_IMAGE_URL, so only it appears (the old golden
    # wrongly carried real-provider keys the hardcoded list always emitted).
    "MOCK_IMAGE_URL=",
]


@pytest.fixture()
def pr_env(tmp_path: Path) -> dict[str, str]:
    """Base environment with a temp catalog exposing test profiles."""
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAA_test test@test\n")
    catalog = tmp_path / "catalog.local.yaml"
    catalog.write_text(_CATALOG)
    return {
        **os.environ,
        "SSH_PUBLIC_KEY_FILE": str(key),
        "EVE_CATALOG_LOCAL": str(catalog),
        "EVE_INSTANCE_REGISTRY": "tests/fixtures/instances.yaml",
        "EVE_INSTANCE_WORKDIR": str(tmp_path / "work"),
        "EVE_STATE_DIR": str(tmp_path / "state"),
    }


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# --------------------------- profile-resolve: --emit env --------------------------- #
def test_profile_resolve_emit_env_byte_identical(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "env", env=pr_env)
    assert result.returncode == 0, result.stderr
    expected = "\n".join(_EXPECTED_ENV_LINES) + "\n"
    assert result.stdout == expected


def test_profile_resolve_emit_env_exact_key_order(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "env", env=pr_env)
    keys = [line.split("=", 1)[0] for line in result.stdout.splitlines()]
    expected_keys = [line.split("=", 1)[0] for line in _EXPECTED_ENV_LINES]
    assert keys == expected_keys


def test_profile_resolve_emit_env_windows_access_user(pr_env: dict[str, str]) -> None:
    """Windows os_family produces Administrator for all access users."""
    result = _run("profile-resolve", "--profile", "pr-windows-aws", "--emit", "env", env=pr_env)
    assert result.returncode == 0, result.stderr
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert lines["ACCESS_BOOTSTRAP_USER"] == "Administrator"
    assert lines["ACCESS_HUMAN_USER"] == "Administrator"
    assert lines["ACCESS_PROVISION_USER"] == "Administrator"
    assert lines["SSH_USER"] == "Administrator"


# --------------------------- profile-resolve: --emit json --------------------------- #
def test_profile_resolve_emit_json(pr_env: dict[str, str]) -> None:
    import json as _json
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "json", env=pr_env)
    assert result.returncode == 0, result.stderr
    data = _json.loads(result.stdout)
    assert data["profile"]["name"] == "pr-ubuntu-qemu"
    assert data["engine"] == "qemu"
    assert data["machine"]["provider"] == "mock-local"
    assert data["os"]["family"] == "ubuntu"
    assert "bundle_packages" in data
    assert data["stack_tags"] == "mock-local"
    # Compact (jq -c) format: no spaces after colons/commas.
    assert '": "' not in result.stdout
    assert '", "' not in result.stdout


# --------------------------- profile-resolve: --emit vagrant --------------------------- #
def test_profile_resolve_emit_vagrant(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "vagrant", env=pr_env)
    assert result.returncode == 0, result.stderr
    assert 'Vagrant.configure("2") do |config|' in result.stdout
    assert 'config.vm.provider "qemu" do |qe|' in result.stdout
    assert 'qe.arch = "aarch64"' in result.stdout
    assert 'config.vm.hostname = "pr-ubuntu-qemu"' in result.stdout


def test_profile_resolve_emit_vagrant_non_ubuntu_exits_2(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-windows-aws", "--emit", "vagrant", env=pr_env)
    assert result.returncode == 2
    assert "only supports os.family=ubuntu" in result.stderr


# --------------------------- profile-resolve: --emit unknown --------------------------- #
def test_profile_resolve_emit_unknown_exits_2(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "bogus", env=pr_env)
    assert result.returncode == 2
    assert "Unsupported --emit format: bogus" in result.stderr


# --------------------------- profile-resolve: --validate --------------------------- #
def test_profile_resolve_validate(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "pr-ubuntu-qemu", "--validate", env=pr_env)
    assert result.returncode == 0
    assert result.stdout == "Profile validated: pr-ubuntu-qemu\n"


# --------------------------- profile-resolve: --output --------------------------- #
def test_profile_resolve_output_to_file(pr_env: dict[str, str], tmp_path: Path) -> None:
    out_file = tmp_path / "out.env"
    result = _run(
        "profile-resolve", "--profile", "pr-ubuntu-qemu", "--emit", "env",
        "--output", str(out_file), env=pr_env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    expected = "\n".join(_EXPECTED_ENV_LINES) + "\n"
    assert out_file.read_text() == expected


# --------------------------- profile-resolve: usage / errors --------------------------- #
def test_profile_resolve_missing_profile_exits_2(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", env=pr_env)
    assert result.returncode == 2
    assert "--profile is required" in result.stderr
    assert "Usage:" in result.stderr


def test_profile_resolve_unknown_arg_exits_2(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--bogus", env=pr_env)
    assert result.returncode == 2
    assert "Unknown argument: --bogus" in result.stderr


def test_profile_resolve_bad_profile_exits_5(pr_env: dict[str, str]) -> None:
    result = _run("profile-resolve", "--profile", "nope", "--emit", "env", env=pr_env)
    assert result.returncode == 5
    assert "Profile not found: nope" in result.stderr


# --------------------------- profile-resolve: SDK fast-path --------------------------- #
def test_profile_resolve_sdk_fast_path(pr_env: dict[str, str]) -> None:
    """EVE_RESOLVED_JSON bypasses catalog load; .instance.name maps to .profile.name."""
    import json as _json
    resolved_json = _json.dumps({
        "instance": {"name": "fast-path-test", "machine": "mock-small"},
        "machine": {"name": "mock-small", "provider": "mock-cloud", "defaults": {}},
        "os": {"id": "mockos-1.0-arm64", "family": "ubuntu"},
        "init": {"id": "ssh-mockos-cloud-init"},
        "location": {"name": "mock-tokyo", "mock-cloud": {"host": "local"}},
        "bundle_packages": ["mock-app"],
        "engine": "qemu",
        "stack_tags": "mock-cloud",
    })
    env = {**pr_env, "EVE_RESOLVED_JSON": resolved_json}
    result = _run("profile-resolve", "--profile", "ignored", "--emit", "env", env=env)
    assert result.returncode == 0, result.stderr
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert lines["PROFILE_NAME"] == "fast-path-test"
    assert lines["ENGINE"] == "qemu"

    json_result = _run("profile-resolve", "--profile", "ignored", "--emit", "json", env=env)
    assert json_result.returncode == 0
    data = _json.loads(json_result.stdout)
    assert data["profile"]["name"] == "fast-path-test"
    assert "instance" in data


# --------------------------- provision: usage / errors --------------------------- #
def test_provision_missing_arg_exits_2(pr_env: dict[str, str]) -> None:
    result = _run("provision", env=pr_env)
    assert result.returncode == 2
    assert "Usage: scripts/provision <instance>" in result.stderr
    assert result.stdout == ""


def test_provision_unknown_os_family_exits_2(pr_env: dict[str, str]) -> None:
    """A profile that resolves to an unknown os_family triggers the dispatch guard."""
    catalog = dedent(
        """\
        profiles:
          - name: pr-unknown-family
            machine: mock-small
            os: mockos-1.0-arm64
            init: generic-ssh
            bundles: [mock-dev]
            location: mock-tokyo
        inits:
          - id: generic-ssh
            providers: [mock-cloud]
        oses:
          - id: mockos-1.0-arm64
            family: freebsd
        """
    )
    key_path = pr_env["SSH_PUBLIC_KEY_FILE"]
    catalog_path = key_path.replace("id_test.pub", "catalog_unknown.yaml")
    Path(catalog_path).write_text(catalog)
    env = {**pr_env, "EVE_CATALOG_LOCAL": catalog_path}
    result = _run("provision", "pr-unknown-family", env=env)
    assert result.returncode == 2
    assert "[provision] unknown os_family: freebsd" in result.stderr


def test_provision_missing_os_dir_exits_2(pr_env: dict[str, str]) -> None:
    """A profile resolving to an OS without a provision tree exits 2.

    The resolve log line goes to stdout before the dir check; stderr carries
    the error. Uses a non-existent OS id so no provision dir is found.
    """
    catalog = dedent(
        """\
        profiles:
          - name: pr-missing-os
            machine: mock-small
            os: ubuntu-99.99-missing
            init: ssh-mockos-cloud-init
            bundles: [mock-dev]
            location: mock-tokyo
        oses:
          - id: ubuntu-99.99-missing
            family: ubuntu
        """
    )
    key_path = pr_env["SSH_PUBLIC_KEY_FILE"]
    catalog_path = key_path.replace("id_test.pub", "catalog_no_os.yaml")
    Path(catalog_path).write_text(catalog)
    env = {**pr_env, "EVE_CATALOG_LOCAL": catalog_path}
    result = _run("provision", "pr-missing-os", env=env)
    assert result.returncode == 2
    assert "OS provisioning directory not found" in result.stderr
    assert "[provision] profile=pr-missing-os os=ubuntu-99.99-missing os_family=ubuntu" in result.stdout


def test_provision_bad_profile_exits_5(pr_env: dict[str, str]) -> None:
    """An unknown profile name propagates profile-resolve exit 5."""
    result = _run("provision", "definitely-not-a-profile", env=pr_env)
    assert result.returncode == 5
