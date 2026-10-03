"""Generic action-exec launcher dispatch (v4.4 §8, Phase 2)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_package_action() -> Any:
    path = ROOT / "scripts" / "package-action"
    loader = importlib.machinery.SourceFileLoader("package_action_v44", str(path))
    spec = importlib.util.spec_from_loader("package_action_v44", loader, origin=str(path))
    assert spec
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    loader.exec_module(module)
    return module


@pytest.fixture
def pa() -> Any:
    return _load_package_action()


def _stub_spine(monkeypatch: pytest.MonkeyPatch, pa: Any, ip: str = "1.2.3.4") -> dict[str, Any]:
    monkeypatch.setattr(
        pa,
        "resolve_env",
        lambda root, inst: {
            "ENGINE": "terraform",
            "OS_FAMILY": "ubuntu",
            "VM_USER_NAME": "alice",
        },
    )
    monkeypatch.setattr(pa, "instance_ip", lambda root, inst: ip)
    captured: dict[str, Any] = {"cmds": [], "envs": []}

    def fake_exec(cmd: list[str], env: dict[str, str]) -> None:
        captured["cmds"].append(cmd)
        captured["envs"].append(env)

    monkeypatch.setattr(pa, "exec_cmd", fake_exec)
    return captured


def test_exec_action_exports_remote_context_and_runs(
    pa: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = tmp_path / "remote-open"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    package = {"id": "pkg", "path": str(tmp_path / "eve-plugin.yaml")}
    action = {"id": "open", "label": "Open", "target": "pkg.open", "exec": "remote-open"}

    captured = _stub_spine(monkeypatch, pa)
    resolved = {"instance": {"name": "inst"}, "package_config": {}}
    operation_env = {"SSH_PUBLIC_KEY_FILE": "/key.pub"}
    pa.run_action_target(
        action, package, "inst", {}, tmp_path, resolved, operation_env
    )

    assert captured["cmds"] == [[str(tmp_path / "remote-open")]]
    env = captured["envs"][0]
    assert env["EVE_REMOTE_IP"] == "1.2.3.4"
    assert env["EVE_REMOTE_USER"] == "alice"
    assert env["EVE_REMOTE_OS_FAMILY"] == "ubuntu"
    assert env["EVE_REMOTE_ENGINE"] == "terraform"
    assert env["EVE_REMOTE_ACTION"] == "pkg.open"
    assert env["EVE_REMOTE_ROOT"] == str(tmp_path)
    assert env["EVE_REMOTE_INSTANCE"] == "inst"


def test_exec_action_wait_for_runs_target_first(pa: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "open").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "wait").write_text("#!/bin/sh\n", encoding="utf-8")
    package = {"id": "pkg", "path": str(tmp_path / "eve-plugin.yaml")}
    open_action = {"id": "open", "label": "Open", "target": "pkg.open", "exec": "open", "wait_for": "pkg.wait"}
    wait_action = {"id": "wait", "label": "Wait", "target": "pkg.wait", "exec": "wait"}
    target_map = {"pkg.wait": {"package": package, "action": wait_action}}

    captured = _stub_spine(monkeypatch, pa)
    resolved = {"instance": {"name": "inst"}, "package_config": {}}
    pa.run_action_target(
        open_action, package, "inst", target_map, tmp_path, resolved, {}
    )

    assert captured["cmds"] == [[str(tmp_path / "wait")], [str(tmp_path / "open")]]


def test_exec_action_missing_exec_fails_loudly(pa: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package = {"id": "pkg", "path": str(tmp_path / "eve-plugin.yaml")}
    action = {"id": "open", "label": "Open", "target": "pkg.open", "exec": "no-such-file"}
    _stub_spine(monkeypatch, pa)
    with pytest.raises(pa.DispatchError, match="launcher exec not found"):
        pa.run_action_target(
            action,
            package,
            "inst",
            {},
            tmp_path,
            {"instance": {"name": "inst"}, "package_config": {}},
            {},
        )


def test_main_uses_full_manifest_for_action_environment(
    pa: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = {
        "exec": "remote-open",
        "id": "open",
        "label": "Open",
        "target": "pkg.open",
    }
    manifest = {
        "_path": str(tmp_path / "eve-plugin.yaml"),
        "_source": "test",
        "actions": [action],
        "config_schema": {
            "secrets": {"token": {"env_var": "PKG_TOKEN"}},
        },
        "id": "pkg",
    }
    monkeypatch.setattr(pa, "process_environment", lambda: {})
    monkeypatch.setattr(
        pa,
        "resolve_instance",
        lambda instance, registry: {
            "instance": {"name": instance},
            "package_config": {},
        },
    )
    monkeypatch.setattr(
        pa,
        "run_json",
        lambda *args: {
            "packages": [{"actions": [action], "id": "pkg", "path": "reduced"}]
        },
    )
    monkeypatch.setattr(
        pa.PluginManifest,
        "load_all",
        classmethod(lambda cls, kind: [manifest]),
    )
    monkeypatch.setattr(pa, "prepare_overlay", lambda instance, registry: "/overlay")
    captured: dict[str, Any] = {}

    def fake_run(
        selected_action: dict[str, Any],
        package: dict[str, Any],
        *args: Any,
    ) -> None:
        captured["action"] = selected_action
        captured["package"] = package

    monkeypatch.setattr(pa, "run_action_target", fake_run)

    assert pa.main(["--instance", "inst", "--package", "pkg", "--action", "open"]) == 0
    assert captured["action"] == action
    assert captured["package"]["config_schema"] == manifest["config_schema"]
