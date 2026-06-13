from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.workdir import Workdir


def test_eve_home_routes_runtime_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))

    assert Workdir.root() == tmp_path
    assert Workdir.eve_dir() == tmp_path / ".eve"
    assert Workdir.generated_dir() == tmp_path / ".generated"
    assert Workdir.instance_registry_path() == tmp_path / ".eve/instances.yaml"
    assert Workdir.overlay_path("demo") == tmp_path / ".generated/instances/demo/catalog.local.yaml"


def test_env_path_overrides_are_expanded_relative_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVE_STATE_DIR", "state-root")

    assert Workdir.state_path("demo") == tmp_path / "state-root/instances/demo.json"
