"""Derive the `catalog-options` view (providers / platforms / bundles / packages)
from already-parsed catalog + plugin data.

This is the assembly that `scripts/catalog-options` used to do inline. It is split
out as pure functions over parsed inputs so two callers can share it:

- the cold script path (`scripts/catalog-options`) passes freshly loaded data, and
- the warm Engine (`eve_sdk.engine`) passes its memoized catalog + plugin set,

producing byte-identical output either way while parsing only once in the warm
case (the script previously triggered three separate disk parses).
"""

from __future__ import annotations

from typing import Any, cast


def provider_os_support(provider_plugins: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Build provider id → set of supported OS ids from contributed catalog.oses."""
    support: dict[str, set[str]] = {}
    for plugin in provider_plugins:
        catalog = plugin.get("catalog")
        if not isinstance(catalog, dict):
            continue
        oses = catalog.get("oses")
        if not isinstance(oses, list):
            continue
        support[plugin["id"]] = {
            entry["id"] for entry in oses if isinstance(entry, dict) and entry.get("id")
        }
    return support


def _os_available_for_provider(
    os_entry: dict[str, Any], provider: str, support: dict[str, set[str]]
) -> bool:
    """Check if an OS is available for a provider via contributed catalog.oses."""
    return os_entry.get("id") in support.get(provider, set())


def _init_available_for_provider(init: dict[str, Any], provider: str) -> bool:
    providers = init.get("providers") if isinstance(init.get("providers"), list) else []
    if providers:
        return provider in providers
    return init.get("provider") is None or init.get("provider") == provider


def build_catalog_options(
    catalog: dict[str, list[dict[str, Any]]],
    provider_plugins: list[dict[str, Any]],
    package_plugins: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the providers/platforms/bundles/packages view from parsed inputs."""
    os_support = provider_os_support(provider_plugins)
    package_plugin_by_id = {plugin["id"]: plugin for plugin in package_plugins}
    providers = sorted(
        {cast(str, machine.get("provider")) for machine in catalog["machines"] if machine.get("provider")}
    )
    platforms: list[dict[str, Any]] = []

    for machine in catalog["machines"]:
        provider = machine.get("provider")
        if not provider:
            continue
        for os_entry in catalog["oses"]:
            supports_raw = machine.get("supports")
            supports = supports_raw if isinstance(supports_raw, dict) else {}
            arches = supports.get("arches") if isinstance(supports.get("arches"), list) else []
            os_ids = supports.get("os_ids") if isinstance(supports.get("os_ids"), list) else []
            if arches and os_entry.get("arch") not in arches:
                continue
            if os_ids and os_entry.get("id") not in os_ids:
                continue
            if not _os_available_for_provider(os_entry, provider, os_support):
                continue
            for init in catalog["inits"]:
                if init.get("os_family") and init.get("os_family") != os_entry.get("family"):
                    continue
                if not _init_available_for_provider(init, provider):
                    continue
                defaults = machine.get("defaults") if isinstance(machine.get("defaults"), dict) else {}
                platforms.append(
                    {
                        "id": ":".join(
                            [
                                str(provider),
                                str(machine.get("name")),
                                str(os_entry.get("id")),
                                str(init.get("id")),
                            ]
                        ),
                        "provider": provider,
                        "machine": machine.get("name"),
                        "os": os_entry.get("id"),
                        "os_family": os_entry.get("family"),
                        "os_version": os_entry.get("version"),
                        "arch": os_entry.get("arch"),
                        "init": init.get("id"),
                        "defaults": defaults,
                    }
                )

    bundles: list[dict[str, Any]] = [
        {"id": bundle.get("id"), "includes": bundle.get("includes") if isinstance(bundle.get("includes"), list) else []}
        for bundle in catalog["bundles"]
    ]

    packages: list[dict[str, Any]] = []
    for package in catalog["packages"]:
        plugin = package_plugin_by_id.get(package.get("id"), {})
        plugin_supports_raw = plugin.get("supports")
        supports = plugin_supports_raw if isinstance(plugin_supports_raw, dict) else {}
        actions = plugin.get("actions") if isinstance(plugin.get("actions"), list) else []
        compatibility = plugin.get("compatibility") if isinstance(plugin.get("compatibility"), list) else []
        install = plugin.get("install") if isinstance(plugin.get("install"), dict) else None
        conflicts_with = plugin.get("conflicts_with") if isinstance(plugin.get("conflicts_with"), list) else []
        desktop = plugin.get("desktop") if isinstance(plugin.get("desktop"), dict) else None
        packages.append(
            {
                "id": package.get("id"),
                "display_name": plugin.get("display_name") or package.get("id"),
                "supports": supports,
                "conflicts_with": conflicts_with,
                "desktop": desktop,
                "installable": install is not None,
                "installable_os_families": list(install.keys()) if install else [],
                "actions": actions,
                "compatibility_enforced": plugin.get("compatibility_enforced") is True,
                "compatibility": compatibility,
            }
        )

    # Locations are chosen at instance-create time (not part of a platform row
    # since WS3). Each catalog location row carries per-provider data under
    # provider-id keys, so a location's providers are its non-"name" keys.
    locations: list[dict[str, Any]] = []
    for location in catalog.get("locations", []):
        if not isinstance(location, dict) or not location.get("name"):
            continue
        loc_providers = sorted(str(key) for key in location if key != "name")
        locations.append({"name": str(location["name"]), "providers": loc_providers})

    return {
        "providers": providers,
        "platforms": sorted(
            platforms,
            key=lambda platform: (
                str(platform["provider"]),
                str(platform["machine"]),
                str(platform["os"]),
                str(platform["init"]),
            ),
        ),
        "locations": sorted(locations, key=lambda location: location["name"]),
        "bundles": sorted(bundles, key=lambda bundle: str(bundle.get("id"))),
        "packages": sorted(packages, key=lambda package: str(package.get("id"))),
    }
