"""Pure helpers for the TUI plugin-source screen.

Wraps eve_sdk.registry (source mutation + recommended catalog) and the
`plugins-pull` materializer. No Textual import here so it stays unit-testable.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from eve_sdk import registry

ROOT = Path(__file__).resolve().parents[1]


def configured_rows() -> list[dict[str, Any]]:
    """Configured sources (merged default + override) with synced state."""
    locked = {item.id for item in registry.read_lock()}
    rows: list[dict[str, Any]] = []
    for source in registry.load_sources():
        rows.append({
            "id": source.id,
            "url": source.url,
            "ref": source.ref or "(unpinned)",
            "auth": source.auth,
            "synced": source.id in locked,
        })
    return rows


def recommended_rows() -> list[dict[str, Any]]:
    """Curated recommended catalog, flagged with whether each is already added."""
    configured = {source.id for source in registry.load_sources()}
    rows: list[dict[str, Any]] = []
    for rec in registry.load_recommended():
        rows.append({
            "id": rec.id,
            "description": rec.description,
            "url": rec.url,
            "ref": rec.ref or "main",
            "tags": list(rec.tags),
            "added": rec.id in configured,
        })
    return rows


def add_recommended(source_id: str) -> tuple[bool, str]:
    recs = {rec.id: rec for rec in registry.load_recommended()}
    rec = recs.get(source_id)
    if rec is None:
        return False, f"unknown recommended id: {source_id}"
    try:
        registry.add_source({"id": rec.id, "url": rec.url, "ref": rec.ref, "auth": rec.auth})
    except registry.RegistryError as error:
        return False, str(error)
    return True, f"added '{rec.id}' — run Pull to materialize"


def add_url(url: str, *, ref: str = "", source_id: str = "", auth: str = "none") -> tuple[bool, str]:
    entry: dict[str, Any] = {"id": source_id or _derive_id(url), "url": url, "ref": ref, "auth": auth}
    try:
        source = registry.add_source(entry)
    except registry.RegistryError as error:
        return False, str(error)
    return True, f"added '{source.id}' — run Pull to materialize"


def remove(source_id: str) -> tuple[bool, str]:
    if registry.remove_source(source_id):
        return True, f"removed '{source_id}' — run Pull to update"
    return False, f"no such source in override: {source_id}"


def pull() -> tuple[bool, str]:
    """Materialize configured sources via scripts/plugins-pull."""
    proc = subprocess.run(
        [str(ROOT / "scripts/plugins-pull")],
        cwd=str(ROOT),
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return False, out or f"plugins-pull exited {proc.returncode}"
    return True, out or "pull complete"


def prune_orphans() -> list[str]:
    """Remove materialized plugins whose source is no longer configured.

    Local-only (no network): lets the provider list reflect a removed source
    immediately on close of the plugin-sources screen, instead of leaving stale
    plugins discoverable until the next pull.
    """
    try:
        return registry.prune_plugins(registry.load_sources())
    except Exception:
        return []


def _derive_id(url: str) -> str:
    base = url.rstrip("/").rsplit("/", 1)[-1]
    return base[:-4] if base.endswith(".git") else base
