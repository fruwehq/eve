from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.plugin_manifest import PluginManifest


def test_plugin_manifest_loads_and_validates_a_provider() -> None:
    # Providers are external (discovered via EVE_PLUGIN_ROOTS, not builtin).
    plugin = next(p for p in PluginManifest.load_all("provider") if p["id"] == "mock-cloud")

    PluginManifest.validate(plugin)

    assert plugin["id"] == "mock-cloud"
    assert PluginManifest.public(plugin)["source"] == "external"


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


def test_plugin_paths_synced_root_is_source_aware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The synced plugins root only exposes exposures backed by a configured
    source; a stale (no-longer-configured) exposure is not discovered. This is
    the durable fix for the lingering Providers list."""
    from eve_sdk.workdir import Workdir

    monkeypatch.delenv("EVE_PLUGIN_ROOTS_EXCLUSIVE", raising=False)
    monkeypatch.delenv("EVE_PLUGIN_ROOTS", raising=False)
    Workdir.set_root(tmp_path)
    Workdir.set_repo_root(tmp_path)
    try:
        plugins = tmp_path / ".eve" / "plugins"
        for sid in ("kept", "stale"):
            exposure = plugins / sid
            exposure.mkdir(parents=True)
            (exposure / "eve-plugin.yaml").write_text(f"id: {sid}\n", encoding="utf-8")
        (tmp_path / ".eve" / "plugin-sources.yaml").write_text(
            "sources:\n  - {id: kept, url: https://example.com/x.git, ref: main, auth: none}\n",
            encoding="utf-8",
        )

        discovered = {PluginManifest.load(p)["id"] for p in PluginManifest.plugin_paths()}
        assert "kept" in discovered
        assert "stale" not in discovered

        # No configured sources ⇒ nothing discovered from the synced root.
        (tmp_path / ".eve" / "plugin-sources.yaml").write_text("sources: []\n", encoding="utf-8")
        assert {PluginManifest.load(p)["id"] for p in PluginManifest.plugin_paths()} == set()
    finally:
        Workdir.reset_overrides()
