from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

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


def test_provider_dispatch_dry_run_happy_path(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/provider-dispatch",
        "--registry",
        str(FIXTURE),
        "--instance",
        "mock-gpu-a",
        "--command",
        "status",
        "--dry-run",
        env={"EVE_INSTANCE_WORKDIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "provider"
    assert payload["provider"] == "mock-cloud"
    assert payload["command"] == "status"
    assert payload["dry_run"] is True


def test_provider_dispatch_rejects_missing_command(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/provider-dispatch",
        "--registry",
        str(FIXTURE),
        "--instance",
        "mock-dev-a",
        "--command",
        "bogus",
        env={"EVE_INSTANCE_WORKDIR": str(tmp_path)},
    )

    assert result.returncode == 1
    assert "has no command: bogus" in result.stderr


def test_package_dispatch_status_dry_run_happy_path(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/package-dispatch",
        "--registry",
        str(FIXTURE),
        "--instance",
        "mock-dev-a",
        "--package",
        "mock-app",
        "--command",
        "status",
        "--dry-run",
        env={"EVE_INSTANCE_WORKDIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["package"] == "mock-app"
    assert payload["command"] == "status"
    assert payload["selected"] is True
    assert payload["status"] == "unknown"


def test_package_dispatch_rejects_unsupported_os(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/package-dispatch",
        "--registry",
        str(FIXTURE),
        "--instance",
        "mock-dev-a",
        "--package",
        "win-only",
        "--command",
        "status",
        "--dry-run",
        env={
            "EVE_INSTANCE_WORKDIR": str(tmp_path),
            "EVE_PLUGIN_ROOTS": f"{os.environ.get('EVE_PLUGIN_ROOTS', '')}:{ROOT / 'tests/fixtures/plugins/packages/win-only'}",
        },
    )

    assert result.returncode == 1
    assert "does not support os family ubuntu" in result.stderr


def test_package_action_dry_run_happy_path() -> None:
    result = run_cmd(
        "scripts/package-action",
        "--instance",
        "mock-dev-a",
        "--package",
        "mock-app",
        "--action",
        "mock-app-info",
        "--dry-run",
        env={"EVE_INSTANCE_REGISTRY": str(FIXTURE)},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "package-action"
    assert payload["target"] == "mock-app.info"


def test_package_action_rejects_unknown_action() -> None:
    result = run_cmd(
        "scripts/package-action",
        "--instance",
        "mock-dev-a",
        "--package",
        "mock-app",
        "--action",
        "missing",
        "--dry-run",
        env={"EVE_INSTANCE_REGISTRY": str(FIXTURE)},
    )

    assert result.returncode == 1
    assert "unknown action missing" in result.stderr
