from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/instances.yaml"


def run_cmd(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / args[0]), *args[1:]],
        cwd=ROOT,
        env=os.environ | (env or {}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_instance_resolve_json_happy_path() -> None:
    result = run_cmd(
        "scripts/instance-resolve",
        "--registry",
        str(FIXTURE),
        "--instance",
        "dev-a",
        "--emit",
        "json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["instance"]["name"] == "dev-a"
    assert payload["provider_plugin"] == "local-qemu"


def test_instance_resolve_rejects_missing_instance() -> None:
    result = run_cmd(
        "scripts/instance-resolve",
        "--registry",
        str(FIXTURE),
        "--instance",
        "missing",
        "--emit",
        "json",
    )

    assert result.returncode == 1
    assert "Instance not found: missing" in result.stderr


def test_instance_create_and_delete_happy_path(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    create = run_cmd(
        "scripts/instance-create",
        "--registry",
        str(registry),
        "--instance",
        "demo-a",
        "--machine",
        "local-qemu-medium",
        "--os",
        "ubuntu-26.04-arm64",
        "--location",
        "tokyo",
        "--bundles",
        "dev-ai",
        env={"EVE_STATE_DIR": str(tmp_path / "state")},
    )
    delete = run_cmd("scripts/instance-delete", "--registry", str(registry), "--instance", "demo-a")

    assert create.returncode == 0, create.stderr
    assert delete.returncode == 0, delete.stderr
    assert not registry.exists()


def test_instance_delete_refuses_recorded_provider_state_without_observed_absent(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    state_dir = tmp_path / "state"
    create = run_cmd(
        "scripts/instance-create",
        "--registry",
        str(registry),
        "--instance",
        "demo-a",
        "--machine",
        "local-qemu-medium",
        "--os",
        "ubuntu-26.04-arm64",
        "--location",
        "tokyo",
        env={"EVE_STATE_DIR": str(state_dir)},
    )
    record = run_cmd(
        "scripts/instance-state",
        "--instance",
        "demo-a",
        "--operation",
        "provider.up",
        "--status",
        "succeeded",
        "--provider-state",
        "running",
        "--desired-state",
        "running",
        env={"EVE_STATE_DIR": str(state_dir)},
    )
    delete = run_cmd(
        "scripts/instance-delete",
        "--registry",
        str(registry),
        "--instance",
        "demo-a",
        env={"EVE_STATE_DIR": str(state_dir)},
    )

    assert create.returncode == 0, create.stderr
    assert record.returncode == 0, record.stderr
    assert delete.returncode == 1
    assert "provider_state=running" in delete.stderr
    assert registry.exists()


def test_instance_create_rejects_duplicate(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "instances": [
                    {
                        "name": "demo-a",
                        "machine": "local-dev",
                        "os": "ubuntu-26.04-amd64",
                        "init": "cloud-init",
                        "location": "local",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = run_cmd(
        "scripts/instance-create",
        "--registry",
        str(registry),
        "--instance",
        "demo-a",
        "--machine",
        "local-dev",
        "--os",
        "ubuntu-26.04-amd64",
        "--location",
        "local",
    )

    assert result.returncode == 1
    assert "instance already exists: demo-a" in result.stderr


def test_instance_status_json_happy_path(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/instance-status",
        "--registry",
        str(FIXTURE),
        "--instance",
        "dev-a",
        "--json",
        env={"EVE_STATE_DIR": str(tmp_path / "state")},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["instance"]["name"] == "dev-a"
    assert "packages" in payload


def test_instance_status_rejects_missing_instance() -> None:
    result = run_cmd("scripts/instance-status", "--registry", str(FIXTURE), "--instance", "missing", "--json")

    assert result.returncode == 1
    assert "Instance not found: missing" in result.stderr


def test_instance_view_aggregate_happy_path(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    registry.write_text("instances:\n  - name: demo-a\n", encoding="utf-8")

    result = run_cmd(
        "scripts/instance-view",
        "--registry",
        str(registry),
        "--aggregate",
        env={"EVE_STATE_DIR": str(tmp_path / "state")},
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["aggregate"]["other"] == 1


def test_instance_view_rejects_unknown_emit() -> None:
    result = run_cmd("scripts/instance-view", "--registry", str(FIXTURE), "--instance", "dev-a", "--emit", "text")

    assert result.returncode == 2
    assert "unsupported emit format" in result.stderr


def test_instance_observe_rejects_missing_instance() -> None:
    result = run_cmd("scripts/instance-observe")

    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_lifecycle_wrappers_reject_missing_instance() -> None:
    for script in ["scripts/instance-ip", "scripts/instance-ssh", "scripts/start", "scripts/stop", "scripts/status"]:
        result = run_cmd(script)

        assert result.returncode == 2
        assert "Usage:" in result.stderr
