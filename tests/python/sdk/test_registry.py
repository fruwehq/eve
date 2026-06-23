"""Registry: source parsing, the git sync engine, and the lockfile."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from eve_sdk.registry import (
    LockedSource,
    RegistryError,
    Source,
    add_source,
    load_recommended,
    load_sources,
    parse_sources,
    prune_plugins,
    read_lock,
    remove_source,
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
    with pytest.raises(RegistryError, match=r"subdir .* not found"):
        sync([src], plugins_dir=tmp_path / "plugins", cache_dir=tmp_path / "cache")


def test_sync_prunes_orphan_exposures(tmp_path: Path) -> None:
    upstream = _make_repo(tmp_path / "up", {"a/marker": "v1"})
    plugins = tmp_path / "plugins"
    src_a = Source(id="a", url=str(upstream), subdir="a", ref="main", auth="none")
    src_b = Source(id="b", url=str(upstream), subdir="a", ref="main", auth="none")
    sync([src_a, src_b], plugins_dir=plugins, cache_dir=tmp_path / "cache")
    assert (plugins / "a").exists() and (plugins / "b").exists()

    # Re-sync with b removed from the configured set: b's exposure is pruned.
    locked = sync([src_a], plugins_dir=plugins, cache_dir=tmp_path / "cache")

    assert [item.id for item in locked] == ["a"]
    assert (plugins / "a").exists()
    assert not (plugins / "b").exists()


def test_prune_plugins_only_removes_symlinks(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    # A symlink sync would have exposed (orphaned: not in the configured set).
    orphan = plugins / "orphan"
    orphan.symlink_to(tmp_path)
    # A real directory the user created — must be left alone even though its
    # name is not a configured source id.
    keep_dir = plugins / "my-stuff"
    keep_dir.mkdir()
    (keep_dir / "file").write_text("x", encoding="utf-8")

    pruned = prune_plugins([], plugins_dir=plugins)

    assert pruned == ["orphan"]
    assert not orphan.exists()
    assert keep_dir.exists()


def test_lock_roundtrip(tmp_path: Path) -> None:
    locked = [
        LockedSource(id="b", url="ub", subdir="x", ref="main", sha="b" * 40),
        LockedSource(id="a", url="ua", subdir="", ref="v1", sha="a" * 40),
    ]
    path = tmp_path / "plugins.lock"
    write_lock(locked, path=path)
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


# --------------------------------------------------------------------------- #
# recommended catalog + source mutation (v4.2 plugin-source management)
# --------------------------------------------------------------------------- #
def test_load_recommended_parses_curated_catalog(tmp_path: Path) -> None:
    path = tmp_path / "recommended-sources.yaml"
    path.write_text(
        "recommended:\n"
        "  - id: eve-providers\n"
        "    description: First-party providers.\n"
        "    url: https://github.com/fruwehq/eve-providers.git\n"
        "    ref: main\n"
        "    auth: none\n"
        "    tags: [providers]\n",
        encoding="utf-8",
    )
    recs = load_recommended(path)
    assert len(recs) == 1
    assert recs[0].id == "eve-providers"
    assert recs[0].auth == "none"
    assert recs[0].tags == ("providers",)


def test_load_recommended_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_recommended(tmp_path / "nope.yaml") == []


def test_load_recommended_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "rec.yaml"
    path.write_text(
        "recommended:\n"
        "  - {id: a, url: https://x/a.git}\n"
        "  - {id: a, url: https://x/b.git}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="duplicate recommended id"):
        load_recommended(path)


def test_add_source_writes_override_and_is_loadable(tmp_path: Path) -> None:
    override = tmp_path / "plugin-sources.yaml"
    source = add_source(
        {"id": "demo", "url": "https://example.com/demo.git", "ref": "v1.0.0", "auth": "none"},
        path=override,
    )
    assert source.id == "demo"
    loaded = load_sources(override)
    assert [s.id for s in loaded] == ["demo"]
    assert loaded[0].ref == "v1.0.0"


def test_add_source_replaces_by_id(tmp_path: Path) -> None:
    override = tmp_path / "plugin-sources.yaml"
    add_source({"id": "demo", "url": "https://example.com/a.git", "ref": "v1"}, path=override)
    add_source({"id": "demo", "url": "https://example.com/b.git", "ref": "v2"}, path=override)
    loaded = load_sources(override)
    assert len(loaded) == 1
    assert loaded[0].url == "https://example.com/b.git"
    assert loaded[0].ref == "v2"


def test_add_source_rejects_unpinned_by_default(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="missing ref"):
        add_source({"id": "demo", "url": "https://example.com/demo.git"}, path=tmp_path / "s.yaml")


def test_remove_source(tmp_path: Path) -> None:
    override = tmp_path / "plugin-sources.yaml"
    add_source({"id": "a", "url": "https://x/a.git", "ref": "v1"}, path=override)
    add_source({"id": "b", "url": "https://x/b.git", "ref": "v1"}, path=override)
    assert remove_source("a", path=override) is True
    assert [s.id for s in load_sources(override)] == ["b"]
    assert remove_source("missing", path=override) is False
