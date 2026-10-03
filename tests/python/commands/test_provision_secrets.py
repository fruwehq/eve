from __future__ import annotations

import importlib.machinery
import importlib.util
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
    assert "Remove-Item -Force -ErrorAction SilentlyContinue" in windows
