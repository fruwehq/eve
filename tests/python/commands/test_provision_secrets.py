from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / name
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.mark.parametrize("script", ["package-provision", "provision"])
def test_shell_environment_values_round_trip_without_expansion(script: str) -> None:
    module = _load_script(script)
    hostile = 'cash$HOME $(printf injected) `printf injected` "quote" \\ slash'
    source = module._env_line("TEST_SECRET", hostile)

    result = subprocess.run(
        ["/bin/sh", "-c", f"{source}; printf %s \"$TEST_SECRET\""],
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout == hostile


@pytest.mark.parametrize("script", ["package-provision", "provision"])
def test_secret_environment_file_is_owner_only(script: str, tmp_path: Path) -> None:
    module = _load_script(script)
    path = tmp_path / "env"

    module._write_private_text(path, "secret")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("script", ["package-provision", "provision"])
def test_staged_path_expands_only_remote_home(script: str) -> None:
    module = _load_script(script)
    filename = 'installer $(printf injected) `printf injected` "quote".deb'
    relative = "provision/downloads/installer/" + filename
    source = module._env_line("INSTALLER", "$HOME/" + relative, remote_home=True)
    result = subprocess.run(
        ["/bin/sh", "-c", source + '; printf %s "$INSTALLER"'],
        env={"HOME": "/remote/home"}, text=True, capture_output=True, check=True,
    )
    assert result.stdout == "/remote/home/" + relative


@pytest.mark.parametrize("existing_mode", [None, 0o644])
def test_private_payload_permissions_are_set_before_writing(
    existing_mode: int | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from eve_sdk.secrets import write_private_text

    path = tmp_path / "env.json"
    if existing_mode is not None:
        path.write_text("old")
        path.chmod(existing_mode)
    original_fdopen = os.fdopen

    def checked_fdopen(fd: int, *args: object, **kwargs: object) -> object:
        # Existing files are secured inside the writer before handle.write.
        handle = original_fdopen(fd, *args, **kwargs)

        class CheckedWriter:
            def __enter__(self) -> object:
                return self

            def __exit__(self, *exc: object) -> None:
                handle.close()

            def fileno(self) -> int:
                return handle.fileno()

            def write(self, text: str) -> int:
                assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
                return handle.write(text)

        return CheckedWriter()

    monkeypatch.setattr(os, "fdopen", checked_fdopen)
    write_private_text(path, '{"secret":"fake"}')
    assert path.read_text() == '{"secret":"fake"}'


def test_windows_partial_package_payload_upload_is_cleaned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    module = _load_script("package-provision-windows")
    tree = tmp_path / "oses" / "test-windows" / "provision"
    (tree / "scripts" / "lib").mkdir(parents=True)
    (tree / "scripts" / "steps").mkdir()
    (tree / "scripts" / "steps" / "install.ps1").write_text("exit 0")
    entry = {
        "id": "test-package", "path": str(tmp_path / "eve-plugin.yaml"),
        "install": {"windows": {"steps": ["install.ps1"], "state_files": ["env.json"]}},
        "config_schema": {"secrets": {"password": {"env_var": "TEST_PASSWORD"}}},
    }
    monkeypatch.setattr(module, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(module, "resolve_env", lambda *args: {"OS_FAMILY": "windows", "OS_ID": "test-windows"})
    monkeypatch.setattr(module, "_plugin_list_json", lambda: {"plugins": [entry]})
    monkeypatch.setattr(module, "instance_package_config", lambda *args: {})
    monkeypatch.setattr(module, "resolved_package_set_environment", lambda *args: {"TEST_PASSWORD": "fake-secret"})
    monkeypatch.setenv("EPHEMERAL_WINDOWS_PASSWORD", "fake-login")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0))
    cleanups: list[str] = []
    monkeypatch.setattr(module, "_instance_ssh", lambda *args: cleanups.append(args[-1]) or 0)

    def upload(label: str, cmd: list[str]) -> int:
        if label == "upload windows package env.json":
            payload = Path(cmd[-2])
            assert stat.S_IMODE(payload.stat().st_mode) == 0o600
            assert "fake-secret" in json.dumps(json.loads(payload.read_text()))
            return 23
        return 0

    monkeypatch.setattr(module, "_ssh_retry", upload)
    assert module.main(["--instance", "test", "--package", "test-package"]) == 23
    assert any("Remove-Item" in cmd and "env.json" in cmd for cmd in cleanups)


@pytest.mark.parametrize("family", ["ubuntu", "windows"])
def test_full_provision_cleans_partial_secret_uploads(
    family: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    module = _load_script("provision")
    tree = tmp_path / "provision"
    steps = tree / "scripts" / "steps"
    steps.mkdir(parents=True)
    for name in ["base.sh", "finish.sh", "human-user.sh", "timezone.sh"]:
        (steps / name).write_text("exit 0")
    monkeypatch.setattr(module.PluginManifest, "os_provision_dir", lambda *args: tree)
    monkeypatch.setattr(module, "_selected_package_environment", lambda *args: ([], {"TIMEZONE": "UTC"}))
    monkeypatch.setenv("EPHEMERAL_WINDOWS_PASSWORD", "fake-login")
    monkeypatch.setattr(
        module.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout='{"plugins": []}'),
    )
    cleanups: list[str] = []
    monkeypatch.setattr(module, "_ssh_retry", lambda *args: cleanups.append(args[1]) or 0)

    def upload(profile: str, label: str, local: str, remote: str) -> int:
        if label in {"upload linux environment", "upload windows provision tree"}:
            path = Path(local) if family == "ubuntu" else Path(local) / "state" / "env.json"
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            return 23
        return 0

    monkeypatch.setattr(module, "_ssh_retry_scp", upload)
    action = module.provision_ubuntu if family == "ubuntu" else module.provision_windows
    assert action("test", {"OS_FAMILY": family, "OS_ID": "test-os"}, tmp_path) == 23
    assert any("environment after upload failure" in label for label in cleanups)


def test_provision_scripts_remove_remote_secret_files() -> None:
    linux = (ROOT / "scripts" / "package-provision").read_text(encoding="utf-8")
    full = (ROOT / "scripts" / "provision").read_text(encoding="utf-8")
    windows = (ROOT / "scripts" / "package-provision-windows").read_text(
        encoding="utf-8"
    )

    assert "trap \\'rm -f" in linux
    assert "$HOME/provision/state/env" in linux
    assert "remove linux provision environment" in full
    assert "remove windows provision environment" in full
    assert "windows_secret_cleanup" in windows
