"""Catalog aggregator — reconstructs the effective catalog by unioning the
central ``config/catalog.yaml`` (+ optional ``config/catalog.local.yaml``) with
plugin-manifest contributions (provider ``catalog`` blocks and package
``bundles`` blocks).

The ``oses`` section is merged by ``id`` with field-level union so that
multiple providers can contribute provider-specific image fields for the same
OS identity row. All other sections (machines, inits, bundles, packages,
locations) are unioned keyed on their id/name with whole-row replace, mirroring
the legacy ``merge_entries`` semantics.

When plugin contributions are empty the result equals the central-catalog load
exactly; when rows relocate into plugin manifests (Phase 0 commit D) the
aggregator seamlessly recombines them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.plugin_manifest import PluginManifest
from eve_sdk.workdir import Workdir

# Times load_catalog() has aggregated from disk. The warm Engine memoizes the
# result; a multi-op session should leave this at 1 (Phase 5 "parse once").
LOAD_COUNT = 0


def load_count() -> int:
    """Return how many times load_catalog() has aggregated from disk."""
    return LOAD_COUNT


def reset_load_count() -> None:
    """Reset the catalog aggregation counter (test helper)."""
    global LOAD_COUNT
    LOAD_COUNT = 0


CATALOG_SECTIONS: dict[str, str] = {
    "bundles": "id",
    "inits": "id",
    "locations": "name",
    "machines": "name",
    "oses": "id",
    "packages": "id",
}

_OSES = "oses"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping, returning ``{}`` for missing or empty files."""
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected a mapping")
    return loaded


def merge_entries(target: list[dict[str, Any]], entries: Any, key: str) -> None:
    """Whole-row replace keyed on ``key``.

    Later entries with the same key replace earlier ones; new keys are appended.
    Entries missing the key, with an empty key, or that are not dicts are
    silently skipped. This mirrors the legacy ``merge_entries`` from
    ``scripts/catalog-options``.
    """
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get(key)
        if entry_id is None or str(entry_id) == "":
            continue
        for index, candidate in enumerate(target):
            if candidate.get(key) == entry_id:
                target[index] = entry
                break
        else:
            target.append(entry)


def merge_os_fields(target: list[dict[str, Any]], entries: Any, key: str) -> None:
    """Field-level union keyed on ``key``.

    Each contribution's fields are overlaid onto the matching existing row so
    that multiple sources (e.g. multiple providers contributing provider-specific
    image fields) combine rather than replacing the whole row. New keys are
    appended as shallow copies.
    """
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get(key)
        if entry_id is None or str(entry_id) == "":
            continue
        for index, candidate in enumerate(target):
            if candidate.get(key) == entry_id:
                merged = dict(candidate)
                merged.update(entry)
                target[index] = merged
                break
        else:
            target.append(dict(entry))


def _merge_section(
    target: list[dict[str, Any]],
    entries: Any,
    section: str,
) -> None:
    key = CATALOG_SECTIONS[section]
    if section == _OSES:
        merge_os_fields(target, entries, key)
    else:
        merge_entries(target, entries, key)


def aggregate(
    central_docs: list[dict[str, Any]],
    plugins: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Reconstruct the effective catalog from central docs and plugin contributions.

    ``central_docs`` are applied in order (base first, overlays later). Plugin
    contributions are applied after all central docs: provider manifests
    contribute ``catalog.machines``, ``catalog.oses``, and ``catalog.inits``;
    package manifests contribute ``bundles``.
    """
    result: dict[str, list[dict[str, Any]]] = {section: [] for section in CATALOG_SECTIONS}

    for doc in central_docs:
        for section in CATALOG_SECTIONS:
            _merge_section(result[section], doc.get(section), section)

    for plugin in plugins or []:
        kind = plugin.get("kind")
        if kind == "provider":
            contribution = plugin.get("catalog")
            if isinstance(contribution, dict):
                for section in ("machines", "oses", "inits"):
                    _merge_section(result[section], contribution.get(section), section)
        elif kind == "package":
            bundles = plugin.get("bundles")
            if isinstance(bundles, list):
                _merge_section(result["bundles"], bundles, "bundles")

    return result


def load_catalog(plugins: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load the effective catalog: central config + plugin contributions.

    Merge order is: central base → plugin contributions → local overlay.
    This ensures user-level overrides (catalog.local.yaml / EVE_CATALOG_LOCAL)
    take precedence over plugin-contributed rows.

    ``plugins`` lets a warm caller (the Engine) pass an already-parsed manifest
    set so the catalog can be aggregated without re-reading every manifest from
    disk. When omitted (the cold script path) manifests are parsed here.
    """
    global LOAD_COUNT
    LOAD_COUNT += 1
    local_value = os.environ.get("EVE_CATALOG_LOCAL")
    local_path = (
        Path(local_value).expanduser().resolve()
        if local_value
        else Workdir.repo_root() / "config/catalog.local.yaml"
    )
    base_doc = _load_yaml(Workdir.repo_root() / "config/catalog.yaml")
    overlay_doc = _load_yaml(local_path)
    manifests = PluginManifest.load_all() if plugins is None else plugins
    result = aggregate([base_doc], manifests)
    if overlay_doc:
        for section in CATALOG_SECTIONS:
            _merge_section(result[section], overlay_doc.get(section), section)
    return result
