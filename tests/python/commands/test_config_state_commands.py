from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def run_cmd(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / args[0]), *args[1:]],
        cwd=ROOT,
        env=os.environ | (env or {}),
        text=True,
        capture_output=True,
        check=False,
    )


def test_config_env_make_happy_path(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("mock-cloud:\n  region: mock-region-1\n", encoding="utf-8")

    result = run_cmd("scripts/config-env", "--make", env={"EVE_CONFIG_PATH": str(config)})

    assert result.returncode == 0, result.stderr
    assert "MOCK_REGION=mock-region-1\n" in result.stdout


def test_config_env_rejects_unknown_flag() -> None:
    result = run_cmd("scripts/config-env", "--bogus")

    assert result.returncode == 2


def test_config_save_write_and_unset(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    env = {"EVE_CONFIG_PATH": str(config)}

    write = run_cmd("scripts/config-save", "mock-cloud", "region", "mock-west-1", env=env)
    unset = run_cmd("scripts/config-save", "--unset", "mock-cloud", "region", env=env)

    assert write.returncode == 0, write.stderr
    assert unset.returncode == 0, unset.stderr
    assert config.read_text(encoding="utf-8") == "{}\n"


def test_config_save_concurrent_writers(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    env = os.environ | {"EVE_CONFIG_PATH": str(config)}
    writers = [
        subprocess.Popen(
            [str(ROOT / "scripts/config-save"), "test_section", f"key_{index}", f"value_{index}"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(20)
    ]

    results = [(*writer.communicate(timeout=30), writer.returncode) for writer in writers]

    assert all(returncode == 0 for _stdout, _stderr, returncode in results), results
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert data["test_section"] == {f"key_{index}": f"value_{index}" for index in range(20)}


def test_config_save_requires_section_and_field() -> None:
    result = run_cmd("scripts/config-save", "mock-cloud")

    assert result.returncode == 2


def test_instance_state_get_and_record_operation(tmp_path: Path) -> None:
    env = {"EVE_STATE_DIR": str(tmp_path)}

    record = run_cmd(
        "scripts/instance-state",
        "--instance",
        "demo",
        "--operation",
        "provider.up",
        "--status",
        "succeeded",
        "--provider-state",
        "running",
        env=env,
    )
    get = run_cmd("scripts/instance-state", "--instance", "demo", "--get", env=env)

    assert record.returncode == 0, record.stderr
    assert get.returncode == 0, get.stderr
    assert json.loads(get.stdout)["provider_state"] == "running"


def test_instance_state_rejects_invalid_observed_json(tmp_path: Path) -> None:
    result = run_cmd(
        "scripts/instance-state",
        "--instance",
        "demo",
        "--observed-json",
        "[]",
        env={"EVE_STATE_DIR": str(tmp_path)},
    )

    assert result.returncode == 2
    assert "observed_json must be an object" in result.stderr
