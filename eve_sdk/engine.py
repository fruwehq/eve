"""Warm, in-process execution engine (v4.0 Phase 5).

Cold path (today): every `scripts/*` invocation is a fresh Python process that
re-parses the catalog and every plugin manifest, then does one operation and
exits. The TUI spawns one such process per data refresh and per op; some scripts
even spawn *other* scripts. Across an interactive session or a scripted pipeline
that is the same parse paid over and over.

The Engine loads the catalog and plugin manifests **once** and reuses them across
many operations. The TUI, `eve batch`/session mode, and scripted callers share a
single Engine, so an N-op session parses catalog+plugins a single time. The
memoized parse is invalidated only when the on-disk manifest set actually changes
(detected via PluginManifest.fingerprint()), e.g. after `eve pull` re-materializes
plugins under a long-lived TUI session.

This module owns only the warm caching + shared parse. Operation semantics live in
the existing eve_sdk modules (package_dispatch, provider_command, instance_dispatch,
resolve, state); the Engine reuses them so behavior stays identical to the scripts.
"""

from __future__ import annotations

from typing import Any

from eve_sdk import catalog as _catalog
from eve_sdk.plugin_manifest import PluginManifest


class Engine:
    """A warm handle over the catalog and plugin manifests.

    Construct once and reuse: ``catalog()`` and ``plugins()`` parse from disk on
    first use and are memoized thereafter. Call ``reload()`` to force a re-parse,
    or rely on the automatic fingerprint check which drops the cache when the
    discovered manifest set changes on disk.
    """

    def __init__(self) -> None:
        self._catalog: dict[str, list[dict[str, Any]]] | None = None
        self._plugins: list[dict[str, Any]] | None = None
        self._fingerprint: tuple[tuple[str, int], ...] | None = None

    # ---- shared parse (the warm core) ---------------------------------- #

    def plugins(self, kind: str | None = None) -> list[dict[str, Any]]:
        """Return the merged plugin manifest set, parsed once and memoized.

        ``kind`` ("provider"/"package") filters the cached set without re-parsing.
        """
        self._ensure_fresh()
        if self._plugins is None:
            self._plugins = PluginManifest.load_all()
        if kind:
            return [plugin for plugin in self._plugins if plugin.get("kind") == kind]
        return self._plugins

    def catalog(self) -> dict[str, list[dict[str, Any]]]:
        """Return the effective catalog, aggregated once and memoized.

        Reuses the memoized plugin set so the manifests are not re-parsed just to
        rebuild the catalog.
        """
        self._ensure_fresh()
        if self._catalog is None:
            self._catalog = _catalog.load_catalog(plugins=self.plugins())
        return self._catalog

    def reload(self) -> None:
        """Drop all memoized state so the next access re-parses from disk."""
        self._catalog = None
        self._plugins = None
        self._fingerprint = None

    # ---- cache invalidation -------------------------------------------- #

    def _ensure_fresh(self) -> None:
        """Invalidate the cache if the on-disk manifest set changed.

        The first call records the fingerprint; later calls compare and clear the
        memoized parse if it drifted (e.g. `eve pull` ran in another process while
        a TUI session was open). Cheap: stat() over the discovered manifests.
        """
        current = PluginManifest.fingerprint()
        if self._fingerprint is None:
            self._fingerprint = current
        elif current != self._fingerprint:
            self._catalog = None
            self._plugins = None
            self._fingerprint = current


_DEFAULT: Engine | None = None


def default_engine() -> Engine:
    """Return the process-wide shared Engine, creating it on first use.

    Scripts, the CLI, and the TUI use this so they share one warm parse within a
    process. Tests that need isolation construct their own ``Engine()``.
    """
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Engine()
    return _DEFAULT
