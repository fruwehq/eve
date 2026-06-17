from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.config import ConfigEnv


def test_config_env_merges_defaults_and_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    defaults = tmp_path / "defaults.yaml"
    local = tmp_path / "config.yaml"
    defaults.write_text("global:\n  ssh_public_key_file: ~/id.pub\n  timezone: UTC\n", encoding="utf-8")
    local.write_text("global:\n  timezone: Asia/Tokyo\n", encoding="utf-8")

    env = ConfigEnv.environment(defaults, local)

    assert env["SSH_PUBLIC_KEY_FILE"] == str(tmp_path / "home/id.pub")
    assert env["TIMEZONE"] == "Asia/Tokyo"


def test_config_env_rejects_structured_values(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("global:\n  timezone: [UTC]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="structured config values must be scalars"):
        ConfigEnv.environment(defaults, tmp_path / "missing.yaml")


def test_config_env_emit_make(tmp_path: Path) -> None:
    # The config->env mapping is contributed by the (hermetic) mock-cloud
    # provider's config_schema: config.region -> MOCK_REGION.
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("mock-cloud:\n  region: mock-region-2\n", encoding="utf-8")

    assert ConfigEnv.emit("--make", defaults, tmp_path / "missing.yaml") == "MOCK_REGION=mock-region-2\n"
