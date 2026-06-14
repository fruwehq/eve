"""Tests for the ``eve plugin test`` conformance harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from eve_sdk.plugin_test import PluginTestResult, run_plugin_test

PROVIDER_CMDS = ["resolve", "init", "plan", "up", "down", "start", "stop", "status", "ip", "ssh", "validate"]
PACKAGE_CMDS = ["install", "status", "down"]

_ACCESS_UBUNTU = {
    "bootstrap_user": {"value": "ubuntu"},
    "provision_user": {"value": "ubuntu"},
    "human_user": {"value": "ubuntu"},
}


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _plugin_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_exec(d: Path, name: str = "run") -> str:
    (d / name).write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    return name


def _write_manifest(d: Path, manifest: dict[str, Any]) -> Path:
    yaml_path = d / "eve-plugin.yaml"
    yaml_path.write_text(yaml.dump(manifest, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return yaml_path


def _valid_provider(d: Path, **extra: Any) -> Path:
    exec_name = _write_exec(d)
    manifest: dict[str, Any] = {
        "api_version": "eve.plugin/v1",
        "kind": "provider",
        "id": "testprov",
        "display_name": "Test Provider",
        "commands": {cmd: {"exec": exec_name} for cmd in PROVIDER_CMDS},
        "access": {"ubuntu": _ACCESS_UBUNTU},
        "supports": {"engines": ["terraform"], "kinds": ["vm"]},
        "env": [],
    }
    manifest.update(extra)
    return _write_manifest(d, manifest)


def _valid_package(d: Path, **extra: Any) -> Path:
    exec_name = _write_exec(d)
    manifest: dict[str, Any] = {
        "api_version": "eve.plugin/v1",
        "kind": "package",
        "id": "testpkg",
        "display_name": "Test Package",
        "commands": {cmd: {"exec": exec_name} for cmd in PACKAGE_CMDS},
        "supports": {"os_families": ["ubuntu"]},
        "env": [],
    }
    manifest.update(extra)
    return _write_manifest(d, manifest)


def _failed_names(result: PluginTestResult) -> list[str]:
    return [c.name for c in result.checks if not c.passed]


# ---------------------------------------------------------------------------
# Valid plugins pass
# ---------------------------------------------------------------------------

class TestValidPluginsPass:
    def test_valid_provider_passes(self, tmp_path: Path) -> None:
        result = run_plugin_test(_valid_provider(_plugin_dir(tmp_path, "prov")))
        assert result.passed, _failed_names(result)

    def test_valid_package_passes(self, tmp_path: Path) -> None:
        result = run_plugin_test(_valid_package(_plugin_dir(tmp_path, "pkg")))
        assert result.passed, _failed_names(result)

    def test_provider_with_requires_passes(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_provider(_plugin_dir(tmp_path, "prov-req"), requires={"eve": "^4.0"})
        )
        assert result.passed, _failed_names(result)


# ---------------------------------------------------------------------------
# Provider boundary violations
# ---------------------------------------------------------------------------

class TestProviderBoundaryViolations:
    def test_provider_missing_ssh_fails(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "prov-no-ssh")
        exec_name = _write_exec(d)
        manifest = {
            "api_version": "eve.plugin/v1",
            "kind": "provider",
            "id": "noproto",
            "display_name": "No SSH",
            "commands": {cmd: {"exec": exec_name} for cmd in PROVIDER_CMDS if cmd != "ssh"},
            "access": {"ubuntu": _ACCESS_UBUNTU},
            "supports": {"engines": ["terraform"], "kinds": ["vm"]},
            "env": [],
        }
        result = run_plugin_test(_write_manifest(d, manifest))
        assert not result.passed

    def test_provider_missing_access_fails(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "prov-no-access")
        exec_name = _write_exec(d)
        manifest = {
            "api_version": "eve.plugin/v1",
            "kind": "provider",
            "id": "noaccess",
            "display_name": "No Access",
            "commands": {cmd: {"exec": exec_name} for cmd in PROVIDER_CMDS},
            "supports": {"engines": ["terraform"], "kinds": ["vm"]},
            "env": [],
        }
        result = run_plugin_test(_write_manifest(d, manifest))
        assert not result.passed
        assert any("access" in name and "provider" in name for name in _failed_names(result))


# ---------------------------------------------------------------------------
# Package boundary violations
# ---------------------------------------------------------------------------

class TestPackageBoundaryViolations:
    def test_package_with_init_contribution_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_package(
                _plugin_dir(tmp_path, "pkg-init"),
                catalog={"inits": [{"id": "ssh-ubuntu-cloud-init", "os_family": "ubuntu"}]},
            )
        )
        assert not result.passed
        assert any("init" in name for name in _failed_names(result))

    def test_package_with_access_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_package(
                _plugin_dir(tmp_path, "pkg-access"),
                access={"ubuntu": _ACCESS_UBUNTU},
            )
        )
        assert not result.passed
        assert any("access" in name for name in _failed_names(result))

    def test_package_with_bringup_command_fails(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "pkg-up")
        exec_name = _write_exec(d)
        manifest = {
            "api_version": "eve.plugin/v1",
            "kind": "package",
            "id": "hasup",
            "display_name": "Has Up",
            "commands": {cmd: {"exec": exec_name} for cmd in [*PACKAGE_CMDS, "up"]},
            "supports": {"os_families": ["ubuntu"]},
            "env": [],
        }
        result = run_plugin_test(_write_manifest(d, manifest))
        assert not result.passed
        assert any("bringup" in name for name in _failed_names(result))

    def test_package_with_provider_capability_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_package(
                _plugin_dir(tmp_path, "pkg-cap"),
                capabilities=["host-ssh"],
            )
        )
        assert not result.passed
        assert any("capabilit" in name for name in _failed_names(result))


# ---------------------------------------------------------------------------
# requires.eve core gate
# ---------------------------------------------------------------------------

class TestRequiresCoreGate:
    def test_requires_excluding_core_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_provider(
                _plugin_dir(tmp_path, "prov-bad-req"),
                requires={"eve": ">=5.0"},
            )
        )
        assert not result.passed
        assert any("requires" in name for name in _failed_names(result))

    def test_requires_including_core_passes(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_provider(
                _plugin_dir(tmp_path, "prov-ok-req"),
                requires={"eve": ">=4.0,<5.0"},
            )
        )
        assert result.passed, _failed_names(result)

    def test_requires_invalid_range_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_provider(
                _plugin_dir(tmp_path, "prov-bad-range"),
                requires={"eve": "xyz"},
            )
        )
        assert not result.passed


# ---------------------------------------------------------------------------
# Malformed manifests
# ---------------------------------------------------------------------------

class TestMalformedManifest:
    def test_broken_yaml_fails(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "bad-yaml")
        yaml_path = d / "eve-plugin.yaml"
        yaml_path.write_text("{{{{not valid yaml", encoding="utf-8")
        result = run_plugin_test(yaml_path)
        assert not result.passed

    def test_missing_kind_fails(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "no-kind")
        exec_name = _write_exec(d)
        manifest = {
            "api_version": "eve.plugin/v1",
            "id": "nokind",
            "display_name": "No Kind",
            "commands": {cmd: {"exec": exec_name} for cmd in PACKAGE_CMDS},
            "supports": {"os_families": ["ubuntu"]},
            "env": [],
        }
        result = run_plugin_test(_write_manifest(d, manifest))
        assert not result.passed

    def test_nonexistent_path_fails(self, tmp_path: Path) -> None:
        result = run_plugin_test(tmp_path / "does-not-exist" / "eve-plugin.yaml")
        assert not result.passed


# ---------------------------------------------------------------------------
# Builtin plugin conformance
# ---------------------------------------------------------------------------

class TestBuiltinConformance:
    """Verify shipped builtin plugins conform to the contract."""

    @staticmethod
    def _plugin_paths() -> list[Path]:
        # First-party plugins are external (synced into .eve/plugins) after Phase 3.
        from eve_sdk.plugin_manifest import PluginManifest
        return [Path(p) for p in PluginManifest.plugin_paths()]

    def test_all_builtins_pass(self) -> None:
        paths = self._plugin_paths()
        assert paths, "no plugin manifests found (run `eve pull`)"
        failures: list[str] = []
        for path in paths:
            result = run_plugin_test(path)
            if not result.passed:
                failures.append(f"{path.parent.name}: {_failed_names(result)}")
        assert not failures, "\n".join(failures)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_result_has_checks(self, tmp_path: Path) -> None:
        result = run_plugin_test(_valid_provider(_plugin_dir(tmp_path, "prov")))
        assert len(result.checks) > 0
        assert result.plugin_id == "testprov"
        assert result.kind == "provider"

    def test_failures_property(self, tmp_path: Path) -> None:
        result = run_plugin_test(
            _valid_package(
                _plugin_dir(tmp_path, "pkg-bad"),
                access={"ubuntu": _ACCESS_UBUNTU},
            )
        )
        assert len(result.failures) > 0
        assert all(not f.passed for f in result.failures)

    def test_directory_path_resolves(self, tmp_path: Path) -> None:
        d = _plugin_dir(tmp_path, "prov-dir")
        _valid_provider(d)
        result = run_plugin_test(d)
        assert result.passed, _failed_names(result)
