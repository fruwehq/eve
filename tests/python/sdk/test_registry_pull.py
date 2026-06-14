"""End-to-end `eve pull` (scripts/plugins-pull): sync -> resolve -> lockfile."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str, cwd: Path) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, text=True, capture_output=True, check=True).stdout.strip()


def _make_package_repo(root: Path, pkg_id: str, *, tag: str, requires: dict | None = None) -> Path:
    """A schema-valid single-package source repo, git-tagged with a semver version."""
    root.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "api_version": "eve.plugin/v1",
        "kind": "package",
        "id": pkg_id,
        "display_name": pkg_id,
        "commands": {name: {"exec": f"commands/{name}"} for name in ("install", "status", "down")},
        "supports": {"os_families": ["ubuntu"]},
        "env": [],
    }
    if requires:
        manifest["requires"] = requires
    (root / "eve-plugin.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    cmds = root / "commands"
    cmds.mkdir(exist_ok=True)
    for name in ("install", "status", "down"):
        script = cmds / name
        script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "init", cwd=root)
    _git("tag", tag, cwd=root)
    return root


def _run_pull(eve_home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "EVE_HOME": str(eve_home)}
    return subprocess.run(
        ["poetry", "run", "python", "scripts/plugins-pull", *args],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )


def _write_sources(eve_home: Path, sources: list[dict]) -> None:
    eve_dir = eve_home / ".eve"
    eve_dir.mkdir(parents=True, exist_ok=True)
    (eve_dir / "plugin-sources.yaml").write_text(yaml.safe_dump({"sources": sources}), encoding="utf-8")


def test_pull_syncs_resolves_and_locks(tmp_path: Path) -> None:
    base = _make_package_repo(tmp_path / "base", "base-pkg", tag="v1.3.0")
    dep = _make_package_repo(
        tmp_path / "dep", "dep-pkg", tag="v1.0.0",
        requires={"eve": ">=4.0,<5.0", "plugins": {"base-pkg": ">=1.2,<2.0"}},
    )
    eve_home = tmp_path / "home"
    _write_sources(eve_home, [
        {"id": "base", "url": str(base), "ref": "v1.3.0", "auth": "none"},
        {"id": "dep", "url": str(dep), "ref": "v1.0.0", "auth": "none"},
    ])

    result = _run_pull(eve_home)
    assert result.returncode == 0, result.stderr

    lock = yaml.safe_load((eve_home / ".eve" / "plugins.lock").read_text())
    # sources pinned to concrete SHAs
    shas = {s["id"]: s["sha"] for s in lock["sources"]}
    assert len(shas["base"]) == 40 and len(shas["dep"]) == 40
    # resolver chose one version per plugin id and recorded who required it
    resolved = {p["id"]: p for p in lock["plugins"]}
    assert resolved["base-pkg"]["version"] == "1.3.0"
    assert resolved["dep-pkg"]["version"] == "1.0.0"
    assert "dep-pkg 1.0.0" in resolved["base-pkg"]["required_by"]


def test_pull_fails_clearly_on_dependency_conflict(tmp_path: Path) -> None:
    # two consumers demand incompatible ranges of the same 'base-pkg'; both base
    # versions are available -> no single version satisfies both -> hard error.
    base1 = _make_package_repo(tmp_path / "base1", "base-pkg", tag="v1.5.0")
    base2 = _make_package_repo(tmp_path / "base2", "base-pkg", tag="v2.0.0")
    a = _make_package_repo(tmp_path / "a", "a-pkg", tag="v1.0.0", requires={"plugins": {"base-pkg": "^1"}})
    b = _make_package_repo(tmp_path / "b", "b-pkg", tag="v1.0.0", requires={"plugins": {"base-pkg": ">=2"}})

    eve_home = tmp_path / "home"
    _write_sources(eve_home, [
        {"id": "base1", "url": str(base1), "ref": "v1.5.0", "auth": "none"},
        {"id": "base2", "url": str(base2), "ref": "v2.0.0", "auth": "none"},
        {"id": "a", "url": str(a), "ref": "v1.0.0", "auth": "none"},
        {"id": "b", "url": str(b), "ref": "v1.0.0", "auth": "none"},
    ])

    result = _run_pull(eve_home)
    assert result.returncode == 1
    assert "dependency resolution failed" in result.stderr
    assert "conflict on plugin 'base-pkg'" in result.stderr
    assert "a-pkg 1.0.0 needs base-pkg ^1" in result.stderr
    assert "b-pkg 1.0.0 needs base-pkg >=2" in result.stderr


@pytest.mark.skipif(os.environ.get("EVE_SKIP_SLOW") == "1", reason="opt-out")
def test_pull_frozen_reproduces_locked_set(tmp_path: Path) -> None:
    base = _make_package_repo(tmp_path / "base", "base-pkg", tag="v1.0.0")
    eve_home = tmp_path / "home"
    _write_sources(eve_home, [{"id": "base", "url": str(base), "ref": "v1.0.0", "auth": "none"}])

    assert _run_pull(eve_home).returncode == 0
    lock_before = (eve_home / ".eve" / "plugins.lock").read_text()

    # wipe the materialized plugins, then --frozen must restore from the lock
    import shutil

    shutil.rmtree(eve_home / ".eve" / "plugins")
    frozen = _run_pull(eve_home, "--frozen")
    assert frozen.returncode == 0, frozen.stderr
    assert (eve_home / ".eve" / "plugins" / "base" / "eve-plugin.yaml").exists()
    # lock unchanged by a frozen re-materialize
    assert (eve_home / ".eve" / "plugins.lock").read_text() == lock_before
