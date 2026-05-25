from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / args[0]), *args[1:]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_catalog_options_json_happy_path() -> None:
    result = run_cmd("scripts/catalog-options", "--json")

    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert "vultr" in doc["providers"]
    assert doc["platforms"]


def test_catalog_options_rejects_unknown_flag() -> None:
    result = run_cmd("scripts/catalog-options", "--bogus")

    assert result.returncode == 2


def test_plugin_list_provider_json_happy_path() -> None:
    result = run_cmd("scripts/plugin-list", "--kind", "provider", "--json")

    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert any(plugin["id"] == "vultr" for plugin in doc["plugins"])


def test_plugin_list_rejects_unknown_kind() -> None:
    result = run_cmd("scripts/plugin-list", "--kind", "bogus")

    assert result.returncode == 2


def test_instance_list_json_happy_path(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    registry.write_text("instances:\n  - name: demo\n    machine: m\n    os: ubuntu\n    location: local\n", encoding="utf-8")

    result = run_cmd("scripts/instance-list", "--registry", str(registry), "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["instances"][0]["name"] == "demo"


def test_instance_list_rejects_unknown_flag() -> None:
    result = run_cmd("scripts/instance-list", "--bogus")

    assert result.returncode == 2


def test_instance_paths_json_happy_path(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    registry.write_text("instances:\n  - name: demo\n", encoding="utf-8")

    result = run_cmd("scripts/instance-paths", "--registry", str(registry), "--instance", "demo", "--emit", "json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["INSTANCE_NAME"] == "demo"


def test_instance_paths_rejects_missing_instance(tmp_path: Path) -> None:
    registry = tmp_path / "instances.yaml"
    registry.write_text("instances:\n  - name: demo\n", encoding="utf-8")

    result = run_cmd("scripts/instance-paths", "--registry", str(registry), "--instance", "missing")

    assert result.returncode == 1
    assert "instance not found" in result.stderr
