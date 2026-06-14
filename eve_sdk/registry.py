"""External plugin registry: sources, sync engine, and lockfile.

A *source* is the unit `(url, subdir, ref)` — a single repo can contribute
multiple independent subfolders, each pinned to its own ref. The sync engine
keys its working copies by `(url, ref)` so multiple refs of one repo coexist,
sparse-checks-out each `subdir`, resolves the ref to a concrete commit SHA, and
records the resolved set in `.eve/plugins.lock` for reproducible re-materialize.

Auth model (no secret is ever written by eve):
- ``ssh``  : use the user's ssh-agent / keys (SSH remotes).
- ``token``: use ``gh``/``GH_TOKEN`` via git's credential helper for HTTPS.
- ``none`` : public HTTPS.

This module is import-safe and side-effect free at module load; all git work is
behind explicit functions so it is drivable from pytest with local repos.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.workdir import Workdir

ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
VALID_AUTH = ("ssh", "token", "none")


class RegistryError(Exception):
    """Raised for malformed sources, lockfiles, or sync failures."""


@dataclass(frozen=True)
class Source:
    """One pinned `(url, subdir, ref)` plugin source."""

    id: str
    url: str
    subdir: str
    ref: str
    auth: str

    @property
    def worktree_key(self) -> str:
        """Stable key for the `(url, ref)` working copy shared across subdirs."""
        digest = hashlib.sha256(f"{self.url}\0{self.ref}".encode()).hexdigest()[:16]
        return digest


@dataclass(frozen=True)
class LockedSource:
    """A source resolved to a concrete commit SHA."""

    id: str
    url: str
    subdir: str
    ref: str
    sha: str


# --------------------------------------------------------------------------- #
# Source parsing
# --------------------------------------------------------------------------- #
def parse_sources(doc: Any, *, allow_unpinned: bool = False) -> list[Source]:
    """Parse + validate the `sources:` list from a plugin-sources document."""
    if not isinstance(doc, dict):
        raise RegistryError("sources file must be a map")
    raw = doc.get("sources") or []
    if not isinstance(raw, list):
        raise RegistryError("sources must be a list")

    seen_ids: set[str] = set()
    sources: list[Source] = []
    for index, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise RegistryError(f"source {index} must be a map")
        source = _parse_one(index, entry, allow_unpinned=allow_unpinned)
        if source.id in seen_ids:
            raise RegistryError(f"duplicate source id: {source.id}")
        seen_ids.add(source.id)
        sources.append(source)
    return sources


def _parse_one(index: int, entry: dict[str, Any], *, allow_unpinned: bool) -> Source:
    plugin_id = entry.get("id")
    url = entry.get("url")
    subdir = entry.get("subdir") or ""
    ref = entry.get("ref") or ""
    auth = entry.get("auth") or "ssh"

    if not isinstance(plugin_id, str) or not ID_RE.match(plugin_id):
        raise RegistryError(f"source {index}: id must match [a-z][a-z0-9-]*")
    if not isinstance(url, str) or not url:
        raise RegistryError(f"source {plugin_id}: url must be a non-empty string")
    if not isinstance(subdir, str) or not isinstance(ref, str):
        raise RegistryError(f"source {plugin_id}: subdir and ref must be strings")
    if auth not in VALID_AUTH:
        raise RegistryError(f"source {plugin_id}: auth must be one of {', '.join(VALID_AUTH)}")
    clean_subdir = subdir.strip("/")
    if _is_unsafe_subdir(clean_subdir):
        raise RegistryError(f"source {plugin_id}: subdir must be a relative path inside the repo")
    if not ref and not allow_unpinned:
        raise RegistryError(
            f"source {plugin_id} is missing ref; set EVE_ALLOW_UNPINNED_PLUGINS=1 to allow this"
        )
    return Source(id=plugin_id, url=url, subdir=clean_subdir, ref=ref, auth=auth)


def _is_unsafe_subdir(subdir: str) -> bool:
    return ".." in Path(subdir).parts


def default_sources_path() -> Path:
    """Committed default source list (the first-party fruwehq repos)."""
    return Workdir.repo_root() / "config/plugin-sources.yaml"


def load_sources(path: Path | None = None, *, allow_unpinned: bool | None = None) -> list[Source]:
    """Load sources. With no explicit *path*, merge the committed default
    (`config/plugin-sources.yaml`) with the local override
    (`.eve/plugin-sources.yaml`); a source id in the local file overrides the
    default. With an explicit *path*, read only that file."""
    if allow_unpinned is None:
        allow_unpinned = os.environ.get("EVE_ALLOW_UNPINNED_PLUGINS") == "1"
    override = os.environ.get("EVE_PLUGIN_SOURCES")
    if path is not None:
        files = [path]
    elif override:
        # Single explicit sources file; bypasses the committed default + local merge.
        files = [Path(override)]
    else:
        files = [default_sources_path(), Workdir.plugin_sources_path()]
    merged: dict[str, Source] = {}
    for target in files:
        if target is None or not target.exists():
            continue
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
        for source in parse_sources(doc, allow_unpinned=allow_unpinned):
            merged[source.id] = source
    return list(merged.values())


# --------------------------------------------------------------------------- #
# Git sync engine
# --------------------------------------------------------------------------- #
def _git(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RegistryError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _auth_env(auth: str) -> dict[str, str]:
    """Build a git env for the source's auth mode (never persists a secret)."""
    env = dict(os.environ)
    # Fail fast instead of hanging on an interactive credential/host prompt.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    if auth == "ssh":
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    elif auth == "token":
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            # Inject via an ephemeral askpass-free header; never written to disk.
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {token}"
    return env


def sync(
    sources: list[Source],
    *,
    plugins_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> list[LockedSource]:
    """Materialize every source and return the lockfile entries (resolved SHAs).

    Working copies are keyed by `(url, ref)` under *cache_dir*; each source's
    `subdir` is sparse-checked-out and exposed at `plugins_dir/<source-id>`.
    """
    dest_root = plugins_dir or Workdir.plugins_dir()
    cache_root = cache_dir or (Workdir.eve_dir() / "cache" / "sources")
    dest_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    locked: list[LockedSource] = []
    for source in sources:
        worktree = cache_root / source.worktree_key
        env = _auth_env(source.auth)
        _materialize_worktree(source, worktree, env)
        sha = _git("rev-parse", "HEAD", cwd=worktree)
        _expose_subdir(source, worktree, dest_root)
        locked.append(
            LockedSource(id=source.id, url=source.url, subdir=source.subdir, ref=source.ref, sha=sha)
        )
    return locked


def resolve_url(url: str) -> str:
    """Resolve a source url. Remote urls (``scheme://`` or ``user@host:path``) are
    returned as-is; a **local path** is supported as a first-class source kind —
    absolute paths pass through, relative paths resolve against the eve repo root
    (so a sibling checkout like ``../eve-providers`` works without a remote or a
    push). This is the configured alternative to pulling from GitHub."""
    if "://" in url or re.match(r"^[^/]+@[^/]+:", url):
        return url
    path = Path(url).expanduser()
    if not path.is_absolute():
        path = (Workdir.repo_root() / path).resolve()
    return str(path)


def _materialize_worktree(source: Source, worktree: Path, env: dict[str, str]) -> None:
    if (worktree / ".git").is_dir():
        _git("fetch", "--tags", "--prune", "origin", cwd=worktree, env=env)
    else:
        worktree.mkdir(parents=True, exist_ok=True)
        _git("clone", "--no-checkout", resolve_url(source.url), str(worktree), env=env)
    # Sparse-checkout only the subdir (whole repo when subdir is empty).
    if source.subdir:
        _git("sparse-checkout", "set", "--no-cone", source.subdir, cwd=worktree, env=env)
    else:
        _git("sparse-checkout", "disable", cwd=worktree, env=env)
    _git("checkout", source.ref, cwd=worktree, env=env)


def _expose_subdir(source: Source, worktree: Path, dest_root: Path) -> None:
    """Point `plugins_dir/<id>` at the source's subdir within its worktree."""
    target = (worktree / source.subdir) if source.subdir else worktree
    if not target.is_dir():
        raise RegistryError(f"source {source.id}: subdir {source.subdir!r} not found at ref {source.ref}")
    link = dest_root / source.id
    if link.is_symlink() or link.exists():
        if link.is_symlink() or link.is_file():
            link.unlink()
        else:
            import shutil

            shutil.rmtree(link)
    link.symlink_to(target)


# --------------------------------------------------------------------------- #
# Lockfile
# --------------------------------------------------------------------------- #
def lock_path() -> Path:
    return Workdir.eve_dir() / "plugins.lock"


def write_lock(
    locked: list[LockedSource],
    resolved: list[dict[str, Any]] | None = None,
    path: Path | None = None,
) -> None:
    """Write `.eve/plugins.lock` with the pinned sources and (optionally) the
    resolved plugin set (each ``{id, version, source_id, required_by}``)."""
    target = path or lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "version": 1,
        "sources": [
            {"id": item.id, "url": item.url, "subdir": item.subdir, "ref": item.ref, "sha": item.sha}
            for item in sorted(locked, key=lambda item: item.id)
        ],
    }
    if resolved is not None:
        doc["plugins"] = sorted(resolved, key=lambda item: str(item.get("id")))
    target.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def read_lock(path: Path | None = None) -> list[LockedSource]:
    target = path or lock_path()
    if not target.exists():
        return []
    doc = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    out: list[LockedSource] = []
    for entry in doc.get("sources") or []:
        out.append(
            LockedSource(
                id=entry["id"],
                url=entry["url"],
                subdir=entry.get("subdir", ""),
                ref=entry.get("ref", ""),
                sha=entry["sha"],
            )
        )
    return out
