from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.plugin_manifest import PluginManifest


def test_plugin_manifest_loads_and_validates_builtin_provider() -> None:
    plugin = PluginManifest.load(Path("plugins/providers/vultr/eve-plugin.yaml"))

    PluginManifest.validate(plugin)

    assert plugin["id"] == "vultr"
    assert PluginManifest.public(plugin)["source"] == "builtin"


def test_plugin_manifest_rejects_missing_command(tmp_path: Path) -> None:
    command = tmp_path / "cmd"
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    manifest = {
        "_path": str(tmp_path / "eve-plugin.yaml"),
        "api_version": "eve.plugin/v1",
        "kind": "package",
        "id": "bad",
        "display_name": "Bad",
        "commands": {"install": {"exec": str(command)}},
        "env": [],
        "supports": {},
    }

    with pytest.raises(ValueError, match="required property"):
        PluginManifest.validate(manifest)
