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

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from eve_sdk import catalog as _catalog
from eve_sdk.catalog_view import build_catalog_options
from eve_sdk.instance_view import (
    build_aggregate,
    build_instance_rows,
    build_instance_view,
    build_statuses,
)
from eve_sdk.package_dispatch import dispatch_package
from eve_sdk.plugin_manifest import PluginManifest
from eve_sdk.provider_command import dispatch_instance_command, dispatch_provider_command
from eve_sdk.resolve import default_registry_path, resolve_instance
from eve_sdk.workdir import Workdir


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

    # ---- derived read views (served from the memo) --------------------- #

    def catalog_options(self) -> dict[str, Any]:
        """The providers/platforms/bundles/packages view (== `catalog-options --json`).

        Assembled from the memoized catalog + plugin set, so repeated calls within
        a session add no disk parses.
        """
        return build_catalog_options(
            self.catalog(),
            self.plugins(kind="provider"),
            self.plugins(kind="package"),
        )

    def plugin_list(self, kind: str | None = None) -> list[dict[str, Any]]:
        """Public manifest views (== `plugin-list [--kind K] --json` `plugins`).

        The same `PluginManifest.public` projection the script emits, served from
        the memoized parse instead of a fresh disk read + file cache.
        """
        return [PluginManifest.public(plugin) for plugin in self.plugins(kind=kind)]

    def instance_rows(self, registry_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
        """Concrete instances from the registry (== `instance-list --json` ``instances``)."""
        return build_instance_rows(registry_path)

    def instance_view(
        self,
        name: str,
        *,
        registry_path: str | os.PathLike[str] | None = None,
        observe: bool = False,
    ) -> dict[str, Any]:
        """Full instance view (== `instance-view --instance <name> [--observe]`).

        Reuses the memoized catalog + plugin set for resolve + assembly, so an
        N-read session parses catalog/plugins exactly once. When ``observe`` is
        set, the live ``provider.status`` subprocess boundary is run first (it
        has to — it shells to the provider plugin); everything else stays warm.
        """
        if observe:
            self._run_observe(name, registry_path)
        # resolve + dispatch consume the public projection (it carries `path`),
        # matching the cold path's plugin-list --json input; catalog aggregation
        # stays on the raw self.plugins() set.
        resolved = resolve_instance(name, registry_path, catalog=self.catalog(), plugins=self.plugin_list())
        return build_instance_view(
            name,
            resolved=resolved,
            package_plugins=self.plugin_list(kind="package"),
            provider_plugins=self.plugin_list(kind="provider"),
        )

    def instance_statuses(
        self, registry_path: str | os.PathLike[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Last-known status for every instance (== `instance-view --statuses`).

        A fast registry+state sweep; no catalog or plugin parse happens here.
        """
        return build_statuses(registry_path)

    def instance_aggregate(
        self, registry_path: str | os.PathLike[str] | None = None
    ) -> dict[str, int]:
        """Aggregate status counts (== `instance-view --aggregate`)."""
        return build_aggregate(registry_path)

    # ---- op methods (in-process; reuse the dispatchers) ---------------- #

    def package(
        self,
        instance: str,
        package_id: str,
        command: str,
        *,
        registry_path: str | None = None,
        dry_run: bool = False,
        yes: bool = False,
        on_output: Callable[[str], None] | None = None,
    ) -> int:
        """Run a package command via the in-process dispatcher (== `package-dispatch`).

        Resolve + plugin lookup reuse the memoized catalog/plugins; the plugin
        command itself still runs as a subprocess (that is the plugin command
        boundary). ``on_output`` (if given) receives each output line for a UI
        to render progress; otherwise output flows to stdout/stderr as the cold
        script's does. Returns the exit code (0 on success).
        """
        return dispatch_package(
            instance,
            package_id,
            command,
            registry_path=registry_path,
            dry_run=dry_run,
            yes=yes,
            plugins=self.plugin_list(),
            catalog=self.catalog(),
            on_output=on_output,
        )

    def provider(
        self,
        target: str,
        command: str,
        *,
        registry_path: str | None = None,
        dry_run: bool = False,
        extra_args: tuple[str, ...] | list[str] = (),
        on_output: Callable[[str], None] | None = None,
    ) -> int:
        """Run a provider command via the in-process dispatcher (== `provider-dispatch`).

        ``target`` is an instance name (instance-scoped commands) or a provider
        id (provider-level commands like ``login``). Resolve + plugin lookup
        reuse the memoized catalog/plugins; the provider command itself still
        runs as a subprocess. Returns the exit code (0 on success).
        """
        if self._is_provider_id(target):
            return dispatch_provider_command(
                target,
                command,
                dry_run=dry_run,
                extra_args=extra_args,
                plugins=self.plugin_list(),
                on_output=on_output,
            )
        return dispatch_instance_command(
            target,
            command,
            registry_path=registry_path,
            dry_run=dry_run,
            extra_args=extra_args,
            plugins=self.plugin_list(),
            catalog=self.catalog(),
            on_output=on_output,
        )

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

    # ---- helpers ------------------------------------------------------- #

    def _is_provider_id(self, target: str) -> bool:
        """True when ``target`` matches a known provider plugin id."""
        return any(
            plugin.get("kind") == "provider" and plugin.get("id") == target
            for plugin in self.plugins()
        )

    def _run_observe(
        self,
        instance_name: str,
        registry_path: str | os.PathLike[str] | None,
    ) -> None:
        """Invoke ``scripts/instance-observe`` (the live provider.status boundary)."""
        env: dict[str, str] = {}
        if Path(registry_path or default_registry_path()) != default_registry_path():
            env["EVE_INSTANCE_REGISTRY"] = str(Path(registry_path).resolve())  # type: ignore[arg-type]
        result = subprocess.run(
            [str(Workdir.repo_root() / "scripts/instance-observe"), "--instance", instance_name],
            cwd=Workdir.repo_root(),
            env=os.environ | env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr if result.stderr else result.stdout
            raise RuntimeError(f"observe failed for {instance_name}: {details.strip()}")


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
