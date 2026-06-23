from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eve_sdk.plugin_manifest import CORE_VERSION, PluginManifest

PROVIDER_CMDS = ["resolve", "init", "plan", "up", "down", "start", "stop", "status", "ip", "ssh", "validate"]
PACKAGE_CMDS = ["install", "status", "down"]


def _exec_file(tmp_path: Path) -> str:
    path = tmp_path / "cmd"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    return str(path)


def _provider_manifest(tmp_path: Path, **extra: Any) -> dict[str, Any]:
    exec_path = _exec_file(tmp_path)
    manifest: dict[str, Any] = {
        "_path": str(tmp_path / "eve-plugin.yaml"),
        "api_version": "eve.plugin/v1",
        "kind": "provider",
        "id": "testprov",
        "display_name": "Test Provider",
        "commands": {cmd: {"exec": exec_path} for cmd in PROVIDER_CMDS},
        "access": {
            "ubuntu": {
                "bootstrap_user": {"value": "ubuntu"},
                "provision_user": {"value": "ubuntu"},
                "human_user": {"value": "ubuntu"},
            }
        },
        "supports": {"engines": ["terraform"], "kinds": ["vm"]},
        "env": [],
    }
    manifest.update(extra)
    return manifest


def _package_manifest(tmp_path: Path, **extra: Any) -> dict[str, Any]:
    exec_path = _exec_file(tmp_path)
    manifest: dict[str, Any] = {
        "_path": str(tmp_path / "eve-plugin.yaml"),
        "api_version": "eve.plugin/v1",
        "kind": "package",
        "id": "testpkg",
        "display_name": "Test Package",
        "commands": {cmd: {"exec": exec_path} for cmd in PACKAGE_CMDS},
        "supports": {"os_families": ["ubuntu"]},
        "env": [],
    }
    manifest.update(extra)
    return manifest


# ---------------------------------------------------------------------------
# requires.eve core gate
# ---------------------------------------------------------------------------

class TestRequiresEve:
    def test_valid_eve_range_passes(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"eve": ">=4.0,<5.0"})
        PluginManifest.validate(manifest)

    def test_caret_range_passes(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"eve": "^4.0"})
        PluginManifest.validate(manifest)

    def test_exact_range_passes(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"eve": "4.0"})
        PluginManifest.validate(manifest)

    def test_eve_range_excluding_core_rejected(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"eve": ">=5.0"})
        with pytest.raises(ValueError, match="excludes running core version"):
            PluginManifest.validate(manifest)

    def test_invalid_eve_range_rejected(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"eve": "xyz"})
        with pytest.raises(ValueError, match="invalid range"):
            PluginManifest.validate(manifest)

    def test_requires_without_eve_passes(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(tmp_path, requires={"plugins": {"foo": "^1.0"}})
        PluginManifest.validate(manifest)

    def test_requires_on_package(self, tmp_path: Path) -> None:
        manifest = _package_manifest(tmp_path, requires={"eve": "^4.0"})
        PluginManifest.validate(manifest)

    def test_core_version_is_4_0(self) -> None:
        assert CORE_VERSION == "4.0"


# ---------------------------------------------------------------------------
# config_schema on packages (widened guard)
# ---------------------------------------------------------------------------

class TestPackageConfigSchema:
    def test_package_config_schema_valid(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            config_schema={
                "config": {
                    "setting": {
                        "type": "string",
                        "description": "A package setting",
                        "default": "hello",
                    }
                }
            },
        )
        PluginManifest.validate(manifest)

    def test_package_without_config_schema_still_valid(self, tmp_path: Path) -> None:
        PluginManifest.validate(_package_manifest(tmp_path))

    def test_provider_config_schema_still_valid(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(
            tmp_path,
            config_schema={
                "secrets": {
                    "api_key": {
                        "type": "string",
                        "required": True,
                        "description": "API key",
                        "env_var": "TESTPROV_API_KEY",
                    }
                }
            },
        )
        PluginManifest.validate(manifest)

    def test_config_schema_non_dict_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(tmp_path)
        manifest["config_schema"] = "not-a-map"
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)


# ---------------------------------------------------------------------------
# v4.4 §8: launcher exec/wait_for, vagrant port_forwards, capability tokens
# ---------------------------------------------------------------------------
class TestLauncherAndCapabilities:
    def test_action_exec_and_wait_for_accepted(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            actions=[
                {"id": "open", "label": "Open", "target": "testpkg.open", "exec": "commands/remote-open"},
                {"id": "wait", "label": "Wait", "target": "testpkg.wait", "wait_for": "testpkg.open"},
            ],
        )
        PluginManifest.validate(manifest)

    def test_vagrant_port_forwards_accepted(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            vagrant={
                "port_forwards": [
                    {"guest": 47984, "host": 47984},
                    {"guest": 47998, "host": 47998, "protocol": "udp"},
                ]
            },
        )
        PluginManifest.validate(manifest)

    def test_port_forward_missing_guest_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(tmp_path, vagrant={"port_forwards": [{"host": 47984}]})
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)

    def test_capability_tokens_accepted(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            provides=["session:wayland"],
            requires_capabilities=["capture:unattended"],
            conflicts_capabilities=["session:wayland"],
        )
        PluginManifest.validate(manifest)

    def test_malformed_capability_token_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(tmp_path, provides=["not-a-token"])
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)


# ---------------------------------------------------------------------------
# catalog on provider manifests
# ---------------------------------------------------------------------------

class TestProviderCatalog:
    def test_provider_with_catalog_passes(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(
            tmp_path,
            catalog={
                "machines": [
                    {
                        "name": "test-vm",
                        "kind": "vm",
                        "defaults": {"instance_type": "t3.small"},
                    }
                ],
                "oses": [
                    {"id": "ubuntu-26.04-amd64", "aws_ami_name_pattern": "ubuntu-*"},
                ],
                "inits": [
                    {"id": "ssh-ubuntu-cloud-init", "os_family": "ubuntu"},
                ],
            },
        )
        PluginManifest.validate(manifest)

    def test_catalog_machine_missing_name_rejected(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(
            tmp_path,
            catalog={
                "machines": [{"kind": "vm"}],
            },
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)

    def test_catalog_os_missing_id_rejected(self, tmp_path: Path) -> None:
        manifest = _provider_manifest(
            tmp_path,
            catalog={
                "oses": [{"family": "ubuntu"}],
            },
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)


# ---------------------------------------------------------------------------
# bundles on package manifests
# ---------------------------------------------------------------------------

class TestPackageBundles:
    def test_package_with_bundles_passes(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            bundles=[
                {"id": "my-bundle", "includes": ["testpkg", "docker"]},
            ],
        )
        PluginManifest.validate(manifest)

    def test_bundle_missing_includes_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            bundles=[{"id": "bad-bundle"}],
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)

    def test_bundle_missing_id_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            bundles=[{"includes": ["docker"]}],
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)

    def test_bundle_empty_includes_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            bundles=[{"id": "empty-bundle", "includes": []}],
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)


# ---------------------------------------------------------------------------
# artifacts on package manifests
# ---------------------------------------------------------------------------

class TestPackageArtifacts:
    def test_package_with_artifacts_passes(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            artifacts=[
                {"id": "image", "path": "/output/image.tar", "download": "package.download"},
            ],
        )
        PluginManifest.validate(manifest)

    def test_artifact_missing_id_rejected(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            artifacts=[{"path": "/output/image.tar"}],
        )
        with pytest.raises(ValueError):
            PluginManifest.validate(manifest)

    def test_artifact_minimal_id_only(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            artifacts=[{"id": "minimal"}],
        )
        PluginManifest.validate(manifest)


# ---------------------------------------------------------------------------
# requires.plugins (shape validation only)
# ---------------------------------------------------------------------------

class TestRequiresPlugins:
    def test_requires_plugins_valid(self, tmp_path: Path) -> None:
        manifest = _package_manifest(
            tmp_path,
            requires={
                "eve": "^4.0",
                "plugins": {"docker": ">=1.0,<2.0", "vscode": "^1.0"},
            },
        )
        PluginManifest.validate(manifest)
