"""Behavior parity for the vagrant-* dispatchers (Phase 2 bash->Python port).

Drives scripts/vagrant-up, vagrant-stop, vagrant-destroy as subprocesses and
asserts the CLI contract: usage/missing-arg handling, the ENGINE gate
(not-supported exit 1, with the up/destroy message on stdout and the stop
message on stderr), the PROVIDER gate (unsupported exit 2), and the
no-Vagrantfile branches. No real vagrant install or VM is required.

Note: vagrant-up's `--plan` dry-run seam sits behind an ENGINE=vagrant AND
PROVIDER=local-qemu conjunction. PROVIDER=local-qemu always derives
ENGINE=qemu (see eve_sdk.resolve.engine_for / scripts/profile-resolve), so that
seam is unreachable under the current engine derivation and is not exercised
here -- the port preserves the original branch faithfully.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[3]

_TF_PROFILE = "terraform-test"     # ENGINE=terraform (aws)
_VAGRANT_PROFILE = "vagrant-test"  # ENGINE=vagrant, PROVIDER=local-vagrant

_CATALOG = dedent(
    """\
    machines:
      - name: local-vagrant-medium
        provider: local-vagrant
        kind: vm
        defaults:
          cpus: 2
          memory_mb: 4096
          disk_gb: 20
    inits:
      - id: ssh-vagrant-init
        os_family: ubuntu
        providers: [local-vagrant]
    locations:
      - name: test-loc
        aws:
          availability_zone: ap-northeast-1a
        local-qemu:
          host: local
        local-vagrant:
          host: local
    profiles:
      - name: terraform-test
        machine: aws-cheap-x86
        os: ubuntu-26.04-amd64
        init: ssh-ubuntu-cloud-init
        bundles: []
        location: test-loc
      - name: qemu-test
        machine: local-qemu-medium
        os: ubuntu-26.04-arm64
        init: ssh-ubuntu-cloud-init
        bundles: []
        location: test-loc
      - name: vagrant-test
        machine: local-vagrant-medium
        os: ubuntu-26.04-amd64
        init: ssh-vagrant-init
        bundles: []
        location: test-loc
    """
)


@pytest.fixture()
def vagrant_env(tmp_path: Path) -> dict[str, str]:
    """Base env: temp SSH key + temp catalog (terraform/qemu/vagrant profiles).

    The registry includes a `vagrant-test` instance so scripts/instance-paths can
    resolve its INSTANCE_WORKDIR for the no-Vagrantfile branch tests.
    """
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAA_test_only test@test\n")
    catalog = tmp_path / "catalog.local.yaml"
    catalog.write_text(_CATALOG)
    registry = tmp_path / "instances.yaml"
    registry.write_text(
        dedent(
            """\
            instances:
              - name: vagrant-test
                machine: local-vagrant-medium
                os: ubuntu-26.04-amd64
                init: ssh-vagrant-init
                location: test-loc
                bundles: []
            """
        )
    )
    return {
        **os.environ,
        "SSH_PUBLIC_KEY_FILE": str(key),
        "EVE_CATALOG_LOCAL": str(catalog),
        "EVE_INSTANCE_REGISTRY": str(registry),
        "VM_USER_NAME": "eve-test",
        "EVE_INSTANCE_WORKDIR": str(tmp_path / "work"),
        "EVE_STATE_DIR": str(tmp_path / "state"),
    }


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# --------------------------- usage / missing arg --------------------------- #
@pytest.mark.parametrize("script", ["vagrant-up", "vagrant-stop", "vagrant-destroy"])
def test_missing_arg_prints_usage_and_exits_nonzero(
    script: str, vagrant_env: dict[str, str]
) -> None:
    result = _run(script, env=vagrant_env)
    assert result.returncode != 0
    assert f"Usage: scripts/{script}" in result.stderr
    assert result.stdout == ""


def test_vagrant_up_missing_arg_after_plan_flag(vagrant_env: dict[str, str]) -> None:
    result = _run("vagrant-up", "--plan", env=vagrant_env)
    assert result.returncode != 0
    assert "Usage: scripts/vagrant-up [--plan] <instance>" in result.stderr


# --------------------------- ENGINE gate (exit 1) -------------------------- #
def test_vagrant_up_not_supported_for_non_vagrant_engine(
    vagrant_env: dict[str, str]
) -> None:
    result = _run("vagrant-up", _TF_PROFILE, env=vagrant_env)
    assert result.returncode == 1
    # up prints the not-supported line to STDOUT (no >&2 in the original).
    assert "[vagrant-up] not supported for engine=terraform" in result.stdout
    assert "[vagrant-up] not supported" not in result.stderr


def test_vagrant_up_engine_gate_qemu(vagrant_env: dict[str, str]) -> None:
    result = _run("vagrant-up", "qemu-test", env=vagrant_env)
    assert result.returncode == 1
    assert "[vagrant-up] not supported for engine=qemu" in result.stdout


def test_vagrant_stop_not_supported_for_non_vagrant_engine(
    vagrant_env: dict[str, str]
) -> None:
    result = _run("vagrant-stop", _TF_PROFILE, env=vagrant_env)
    assert result.returncode == 1
    # stop prints the not-supported line to STDERR.
    assert "[vagrant-stop] not supported for engine=terraform" in result.stderr
    assert "[vagrant-stop] not supported" not in result.stdout


def test_vagrant_destroy_not_supported_for_non_vagrant_engine(
    vagrant_env: dict[str, str]
) -> None:
    result = _run("vagrant-destroy", _TF_PROFILE, env=vagrant_env)
    assert result.returncode == 1
    # destroy prints the not-supported line to STDOUT (no >&2 in the original).
    assert "[vagrant-destroy] not supported for engine=terraform" in result.stdout
    assert "[vagrant-destroy] not supported" not in result.stderr


# --------------------------- PROVIDER gate (exit 2) ------------------------ #
def test_vagrant_up_unsupported_local_provider(vagrant_env: dict[str, str]) -> None:
    result = _run("vagrant-up", _VAGRANT_PROFILE, env=vagrant_env)
    assert result.returncode == 2
    assert "[vagrant-up] unsupported local provider=local-vagrant" in result.stderr
    # The provider case exits before the profile= line is printed.
    assert "[vagrant-up] profile=" not in result.stdout


# --------------------------- no-Vagrantfile branches ----------------------- #
def test_vagrant_stop_no_vagrantfile(vagrant_env: dict[str, str]) -> None:
    result = _run("vagrant-stop", _VAGRANT_PROFILE, env=vagrant_env)
    assert result.returncode == 1
    assert "[vagrant-stop] profile=vagrant-test" in result.stdout
    assert (
        "No generated Vagrantfile for instance vagrant-test. Nothing to stop."
        in result.stderr
    )


def test_vagrant_destroy_no_vagrantfile(vagrant_env: dict[str, str]) -> None:
    result = _run("vagrant-destroy", _VAGRANT_PROFILE, env=vagrant_env)
    assert result.returncode == 0
    assert "[vagrant-destroy] profile=vagrant-test" in result.stdout
    assert (
        "No generated Vagrantfile for instance vagrant-test. Nothing to destroy."
        in result.stdout
    )
