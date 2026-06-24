"""Per-instance view assembly (v4.0 Phase 5).

Pure functions over already-parsed inputs that produce the same data the
``scripts/instance-view`` and ``scripts/package-list`` cold paths emit. The
warm Engine (``eve_sdk.engine``) calls these with its memoized catalog + plugin
set; the cold scripts delegate to the same functions with freshly-loaded data.
Output is byte-identical either way, and the warm path parses catalog/plugins
exactly once across an entire session (the Phase 5 invariant).

This is the same extraction pattern ``eve_sdk.catalog_view`` used for
``catalog-options``: lift a script's inline JSON-assembly into a pure function
over parsed inputs, then have both cold script and warm Engine share it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from eve_sdk import state_machine
from eve_sdk.dispatch import support_allowed
from eve_sdk.resolve import default_registry_path, load_any
from eve_sdk.state import State
from eve_sdk.workdir import Workdir

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def instance_paths(instance_name: str) -> dict[str, str]:
    """All instance-scoped filesystem paths (== ``instance-paths --emit json``)."""
    return Workdir.all_paths(instance_name)


# --------------------------------------------------------------------------- #
# Provider actions lookup
# --------------------------------------------------------------------------- #

def provider_actions(
    provider_id: str, provider_plugins: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Look up a provider plugin's declared ``actions`` list.

    Mirrors ``scripts/instance-view.provider_actions`` over an already-parsed
    provider plugin set, instead of subprocess-ing ``plugin-list`` per call.
    """
    plugin = next(
        (entry for entry in provider_plugins if entry.get("id") == provider_id),
        None,
    )
    if not plugin:
        return []
    actions = plugin.get("actions")
    return actions if isinstance(actions, list) else []


# --------------------------------------------------------------------------- #
# Package-list assembly (extracted from scripts/package-list)
# --------------------------------------------------------------------------- #

def compatibility_target(os_family: str, desktop_plugins: list[dict[str, Any]]) -> dict[str, str]:
    """Pick the desktop/session compatibility target for an OS family.

    Data-driven (v4.4 §15): the selected desktop package(s) contribute their
    ``desktop`` manifest metadata (name/session/headless); core no longer
    branches on package ids. When no desktop is selected on ubuntu, the default
    is XFCE/X11 (a core default, not a package id).
    """
    if os_family == "windows":
        return {"platform": "windows", "desktop": "Windows", "session": "Native"}
    if desktop_plugins:
        chosen = sorted(desktop_plugins, key=lambda d: not bool(d.get("headless")))[0]
        return {"platform": os_family, "desktop": str(chosen.get("name", "")),
                "session": str(chosen.get("session", ""))}
    if os_family == "ubuntu":
        return {"platform": "ubuntu", "desktop": "XFCE", "session": "X11"}
    return {"platform": os_family, "desktop": "", "session": ""}


def compatibility_match(plugin: dict[str, Any], target: dict[str, str]) -> bool:
    """Whether a package plugin's compatibility table accepts ``target``.

    Faithful port of ``scripts/package-list.compatibility_match``.
    """
    compatibility_raw = plugin.get("compatibility")
    entries = compatibility_raw if isinstance(compatibility_raw, list) else []
    if plugin.get("compatibility_enforced") is not True:
        return True
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "supported":
            continue
        if entry.get("platform") != target["platform"]:
            continue
        if str(entry.get("desktop") or "") and entry.get("desktop") != target["desktop"]:
            continue
        if str(entry.get("session") or "") and entry.get("session") != target["session"]:
            continue
        return True
    return False


def build_package_rows(
    resolved: dict[str, Any], package_plugins: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Build the per-instance package rows (== ``package-list --json`` payload).

    Faithful port of ``scripts/package-list.build_packages`` body, parameterized
    on the already-parsed package plugin set instead of subprocess-ing
    ``plugin-list``. Returns ``(os_family, packages)``.
    """
    plugin_by_id = {plugin["id"]: plugin for plugin in package_plugins}
    selected_ids = resolved["bundle_packages"]
    desktop_plugins = [
        plugin_by_id[pkg]["desktop"]
        for pkg in selected_ids
        if pkg in plugin_by_id and isinstance(plugin_by_id[pkg].get("desktop"), dict)
    ]
    package_sources = resolved.get("package_sources", {})
    os_doc = resolved["os"]
    os_family = os_doc["family"]
    os_arch = os_doc.get("arch", "")
    os_version = os_doc.get("version", "")
    target = compatibility_target(os_family, desktop_plugins)

    packages: list[dict[str, Any]] = []
    for plugin in sorted(package_plugins, key=lambda entry: entry["id"]):
        supports = plugin.get("supports") or {}
        supported = (
            support_allowed(supports, "os_families", os_family)
            and support_allowed(supports, "arches", os_arch)
            and support_allowed(supports, "os_ids", os_doc["id"])
            and support_allowed(supports, "os_versions", os_version)
            and support_allowed(supports, f"{os_family}_versions", os_version)
        )
        install_raw = plugin.get("install")
        install = install_raw if isinstance(install_raw, dict) else {}
        installable = isinstance(install.get(os_family), dict)
        actions = plugin.get("actions", [])
        conflicts_raw = plugin.get("conflicts_with")
        conflicts = conflicts_raw if isinstance(conflicts_raw, list) else []
        conflict = next((package for package in conflicts if package in selected_ids), None)
        if conflict or not compatibility_match(plugin, target):
            supported = False
            installable = False
            actions = []
        packages.append(
            {
                "id": plugin["id"],
                "display_name": plugin["display_name"],
                "plugin": plugin["id"],
                "selected": plugin["id"] in selected_ids,
                "selected_by": package_sources.get(plugin["id"], []),
                "supported": supported,
                "installable": installable,
                "source": plugin["source"],
                "path": plugin["path"],
                "actions": actions,
            }
        )

    for package_id in selected_ids:
        if package_id in plugin_by_id:
            continue
        packages.append(
            {
                "id": package_id,
                "display_name": package_id,
                "plugin": None,
                "selected": True,
                "selected_by": package_sources.get(package_id, []),
                "supported": False,
                "source": "missing",
                "path": None,
                "actions": [],
            }
        )
    return os_family, packages


# --------------------------------------------------------------------------- #
# Full instance view
# --------------------------------------------------------------------------- #

def build_instance_view(
    instance_name: str,
    *,
    resolved: dict[str, Any],
    package_plugins: list[dict[str, Any]],
    provider_plugins: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the full instance-view object (== ``instance-view --instance``).

    Composes ``State.build_view`` with package rows, paths, and provider
    actions, all derived from already-parsed inputs so the warm Engine reuses
    its memoized catalog + plugin set without re-parsing per call.
    """
    paths = instance_paths(instance_name)
    _os_family, packages = build_package_rows(resolved, package_plugins)
    view = State.build_view(
        instance_name=instance_name, resolved=resolved, packages=packages, paths=paths
    )
    view["provider_actions"] = provider_actions(resolved["provider_plugin"], provider_plugins)
    return view


# --------------------------------------------------------------------------- #
# Statuses / aggregate (the --statuses and --aggregate paths)
# --------------------------------------------------------------------------- #

def _registry_path(registry_path: str | os.PathLike[str] | None) -> Path:
    return Path(registry_path).resolve() if registry_path else default_registry_path()


def build_statuses(registry_path: str | os.PathLike[str] | None = None) -> dict[str, dict[str, Any]]:
    """Last-known status for every instance (== ``instance-view --statuses``).

    Reads persisted state without resolving or live-observing each instance,
    so the instance table can render real state immediately. No catalog or
    plugin parse happens here — this is a fast registry+state sweep.
    """
    registry = load_any(_registry_path(registry_path))
    statuses: dict[str, dict[str, Any]] = {}
    for instance in registry.get("instances", []):
        if not isinstance(instance, dict) or not instance.get("name"):
            continue
        name = str(instance["name"])
        state = State.read(name)
        observed = state.get("observed_state", {})
        status = state_machine.status_with_observed_state(
            {"instance": instance, "state": state, "observed_state": observed},
            {"observed_state": observed},
        )
        inner = status.get("state")
        if isinstance(inner, dict):
            # Add ``effective_provider_state`` so this fast (no-resolve) read is
            # a drop-in for rendering the instance table.
            inner["effective_provider_state"] = state_machine.effective_provider_state(inner)
        statuses[name] = status
    return statuses


def build_aggregate(registry_path: str | os.PathLike[str] | None = None) -> dict[str, int]:
    """Aggregate status counts across the registry (== ``instance-view --aggregate``)."""
    return state_machine.aggregate_summary(build_statuses(registry_path))


# --------------------------------------------------------------------------- #
# Instance rows (for the TUI instance table)
# --------------------------------------------------------------------------- #

def build_instance_rows(registry_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Concrete instances from the registry (== ``instance-list --json`` ``instances``)."""
    registry = load_any(_registry_path(registry_path))
    rows = registry.get("instances", [])
    return rows if isinstance(rows, list) else []
