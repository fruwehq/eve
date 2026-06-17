"""Behavior parity for the tf-* terraform dispatchers (Phase 2 bash->Python port).

Drives scripts/tf-init, tf-plan, tf-apply, tf-destroy as subprocesses and
asserts the CLI contract: usage/missing-arg handling, the ENGINE gate
(no-op vs. not-supported vs. destroy error), and tf-init's EVE_TF_PRINT=1
dry-run. No real terraform/terramate/cloud is required — the engine gate exits
before any terramate call, and the dry-run replaces execution with print lines.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[3]

_TF_PROFILE = "tf-aws-test"  # ENGINE=terraform (mock-cloud), STACK_TAGS=mock-cloud
_QEMU_PROFILE = "qemu-test"  # ENGINE=qemu (mock-local), STACK_TAGS=mock-local
_CATALOG = dedent(
    """\
    profiles:
      - name: tf-aws-test
        machine: mock-small
        os: mockos-1.0-amd64
        init: ssh-mockos-cloud-init
        bundles: [mock-dev]
        location: mock-tokyo
      - name: qemu-test
        machine: mock-vm
        os: mockos-1.0-arm64
        init: ssh-mockos-cloud-init
        bundles: [mock-dev]
        location: mock-tokyo
    """
)


@pytest.fixture()
def tf_env(tmp_path: Path) -> dict[str, str]:
    """Base environment with a temp SSH key + temp catalog exposing both profiles."""
    key = tmp_path / "id_test.pub"
    key.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAA_test_only test@test\n")
    catalog = tmp_path / "catalog.local.yaml"
    catalog.write_text(_CATALOG)
    env = {
        **os.environ,
        "SSH_PUBLIC_KEY_FILE": str(key),
        "EVE_CATALOG_LOCAL": str(catalog),
        "VM_USER_NAME": "eve-test",
        "EVE_INSTANCE_REGISTRY": "tests/fixtures/instances.yaml",
        "EVE_INSTANCE_WORKDIR": str(tmp_path / "work"),
        "EVE_STATE_DIR": str(tmp_path / "state"),
    }
    return env


def _run(script: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT, text=True, capture_output=True, check=False, env=env,
    )


# --------------------------- usage / missing arg --------------------------- #
@pytest.mark.parametrize("script", ["tf-init", "tf-plan", "tf-apply", "tf-destroy"])
def test_missing_arg_prints_usage_and_exits_nonzero(script: str, tf_env: dict[str, str]) -> None:
    result = _run(script, env=tf_env)
    assert result.returncode != 0
    assert f"Usage: scripts/{script} <instance>" in result.stderr
    assert result.stdout == ""


# --------------------------- ENGINE gate: tf-init (no-op) ------------------ #
def test_tf_init_noop_for_non_terraform_engine(tf_env: dict[str, str]) -> None:
    result = _run("tf-init", _QEMU_PROFILE, env=tf_env)
    assert result.returncode == 0
    assert "[tf-init] no-op for engine=qemu" in result.stdout


# --------------------------- ENGINE gate: tf-plan/apply (exit 1) ----------- #
def test_tf_plan_not_supported_for_non_terraform_engine(tf_env: dict[str, str]) -> None:
    result = _run("tf-plan", _QEMU_PROFILE, env=tf_env)
    assert result.returncode == 1
    assert "[tf-plan] not supported for engine=qemu" in result.stdout


def test_tf_apply_not_supported_for_non_terraform_engine(tf_env: dict[str, str]) -> None:
    result = _run("tf-apply", _QEMU_PROFILE, env=tf_env)
    assert result.returncode == 1
    assert "[tf-apply] not supported for engine=qemu" in result.stdout


def test_tf_destroy_not_supported_for_non_terraform_engine(tf_env: dict[str, str]) -> None:
    result = _run("tf-destroy", _QEMU_PROFILE, env=tf_env)
    assert result.returncode == 1
    assert "Error: qemu-test uses engine 'qemu', not terraform" in result.stderr


# --------------------------- tf-init EVE_TF_PRINT dry-run ------------------ #
def test_tf_init_print_mode_skips_workspace_in_profile_mode(tf_env: dict[str, str]) -> None:
    env = {**tf_env, "EVE_TF_PRINT": "1"}
    result = _run("tf-init", _TF_PROFILE, env=env)
    assert result.returncode == 0, result.stderr
    assert "[tf-init] profile=tf-aws-test tags=mock-cloud" in result.stdout
    assert "[tf-init] would run:" in result.stdout
    assert "terraform init -reconfigure" in result.stdout
    assert "terraform workspace" not in result.stdout


def test_tf_init_print_mode_schedules_workspace_in_instance_mode(tf_env: dict[str, str]) -> None:
    instance = "mock-gpu-a"
    env = {**tf_env, "EVE_TF_PRINT": "1", "EVE_INSTANCE_NAME": instance}
    result = _run("tf-init", _TF_PROFILE, env=env)
    assert result.returncode == 0, result.stderr
    assert "terraform init -reconfigure" in result.stdout
    assert f"terraform workspace select -or-create {instance}" in result.stdout
    assert "--eval" in result.stdout
    assert "backend-config=path=" in result.stdout
    assert "backend-config=workspace_dir=" in result.stdout
