"""Registry: source parsing, the git sync engine, and the lockfile."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from eve_sdk.registry import (
    LockedSource,
    RegistryError,
    Source,
    parse_sources,
    read_lock,
    sync,
    write_lock,
)


# --------------------------------------------------------------------------- #
# git fixtures
# --------------------------------------------------------------------------- #
def _git(*args: str, cwd: Path) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, text=True, capture_output=True, check=True
    ).stdout.strip()


def _make_repo(root: Path, files: dict[str, str], *, branch: str = "main") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", branch, cwd=root)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "init", cwd=root)
    return root


# --------------------------------------------------------------------------- #
# parse_sources
# --------------------------------------------------------------------------- #
def test_parse_full_source() -> None:
    doc = {"sources": [{"id": "vultr", "url": "git@x:y.git", "subdir": "vultr", "ref": "v1.0", "auth": "ssh"}]}
    (source,) = parse_sources(doc)
    assert source == Source(id="vultr", url="git@x:y.git", subdir="vultr", ref="v1.0", auth="ssh")


def test_parse_defaults_auth_ssh_and_strips_subdir() -> None:
    doc = {"sources": [{"id": "p", "url": "u", "subdir": "/a/b/", "ref": "main"}]}
    (source,) = parse_sources(doc)
    assert source.auth == "ssh"
    assert source.subdir == "a/b"


def test_parse_rejects_unpinned_without_override() -> None:
    doc = {"sources": [{"id": "p", "url": "u"}]}
    with pytest.raises(RegistryError, match="missing ref"):
        parse_sources(doc)
    assert parse_sources(doc, allow_unpinned=True)[0].ref == ""


@pytest.mark.parametrize(
    "entry, match",
    [
        ({"id": "Bad", "url": "u", "ref": "r"}, "id must match"),
        ({"id": "p", "url": "", "ref": "r"}, "url must be"),
        ({"id": "p", "url": "u", "ref": "r", "auth": "basic"}, "auth must be one of"),
        ({"id": "p", "url": "u", "ref": "r", "subdir": "../escape"}, "relative path inside"),
    ],
)
def test_parse_rejects_invalid(entry: dict, match: str) -> None:
    with pytest.raises(RegistryError, match=match):
        parse_sources({"sources": [entry]})


def test_parse_rejects_duplicate_ids() -> None:
    doc = {"sources": [{"id": "p", "url": "u", "ref": "r"}, {"id": "p", "url": "v", "ref": "s"}]}
    with pytest.raises(RegistryError, match="duplicate source id"):
        parse_sources(doc)


def test_worktree_key_differs_by_ref_same_url() -> None:
    a = Source(id="a", url="u", subdir="", ref="main", auth="none")
    b = Source(id="b", url="u", subdir="", ref="feature", auth="none")
    assert a.worktree_key != b.worktree_key


# --------------------------------------------------------------------------- #
# sync engine + lockfile
# --------------------------------------------------------------------------- #
def test_sync_exposes_subdir_and_resolves_sha(tmp_path: Path) -> None:
    upstream = _make_repo(
        tmp_path / "upstream",
        {"eve/providers/foo/eve-plugin.yaml": "id: foo\n", "readme.md": "x"},
    )
    head = _git("rev-parse", "HEAD", cwd=upstream)

    src = Source(id="foo-src", url=str(upstream), subdir="eve", ref="main", auth="none")
    locked = sync([src], plugins_dir=tmp_path / "plugins", cache_dir=tmp_path / "cache")

    assert locked == [LockedSource(id="foo-src", url=str(upstream), subdir="eve", ref="main", sha=head)]
    exposed = tmp_path / "plugins" / "foo-src"
    assert (exposed / "providers/foo/eve-plugin.yaml").read_text() == "id: foo\n"
    # subdir was sparse-checked-out: the repo root readme is not exposed under the subdir
    assert not (exposed / "readme.md").exists()


def test_sync_two_refs_of_same_repo_coexist(tmp_path: Path) -> None:
    upstream = _make_repo(tmp_path / "up", {"a/marker": "main-content"})
    _git("checkout", "-q", "-b", "feature", cwd=upstream)
    (upstream / "a/marker").write_text("feature-content", encoding="utf-8")
    _git("commit", "-aqm", "feature", cwd=upstream)

    main_src = Source(id="s-main", url=str(upstream), subdir="a", ref="main", auth="none")
    feat_src = Source(id="s-feat", url=str(upstream), subdir="a", ref="feature", auth="none")
    sync([main_src, feat_src], plugins_dir=tmp_path / "plugins", cache_dir=tmp_path / "cache")

    assert (tmp_path / "plugins/s-main/marker").read_text() == "main-content"
    assert (tmp_path / "plugins/s-feat/marker").read_text() == "feature-content"


def test_sync_missing_subdir_fails(tmp_path: Path) -> None:
    upstream = _make_repo(tmp_path / "up", {"a/x": "y"})
    src = Source(id="s", url=str(upstream), subdir="nope", ref="main", auth="none")
    with pytest.raises(RegistryError, match="subdir .* not found"):
        sync([src], plugins_dir=tmp_path / "plugins", cache_dir=tmp_path / "cache")


def test_lock_roundtrip(tmp_path: Path) -> None:
    locked = [
        LockedSource(id="b", url="ub", subdir="x", ref="main", sha="b" * 40),
        LockedSource(id="a", url="ua", subdir="", ref="v1", sha="a" * 40),
    ]
    path = tmp_path / "plugins.lock"
    write_lock(locked, path)
    out = read_lock(path)
    # sorted by id on write
    assert [item.id for item in out] == ["a", "b"]
    assert out[1].sha == "b" * 40


def test_frozen_rematerialize_checks_out_sha(tmp_path: Path) -> None:
    upstream = _make_repo(tmp_path / "up", {"a/marker": "v1"})
    sha_v1 = _git("rev-parse", "HEAD", cwd=upstream)
    (upstream / "a/marker").write_text("v2", encoding="utf-8")
    _git("commit", "-aqm", "v2", cwd=upstream)

    # frozen sync pins ref to the old SHA -> must restore v1 content
    frozen = Source(id="s", url=str(upstream), subdir="a", ref=sha_v1, auth="none")
    sync([frozen], plugins_dir=tmp_path / "plugins", cache_dir=tmp_path / "cache")
    assert (tmp_path / "plugins/s/marker").read_text() == "v1"
