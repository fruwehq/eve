"""Tests for the Phase 0 catalog relocation.

Validates that provider-owned catalog rows (machines, provider-specific OS
image fields) and package-owned bundles have been correctly relocated into
plugin manifests, and that the aggregator reconstructs the full effective
catalog including field-level OS row merges.
"""

from __future__ import annotations

from eve_sdk.catalog import load_catalog
from eve_sdk.plugin_manifest import PluginManifest

# ---------------------------------------------------------------------------
# Provider catalog.oses support sets
# ---------------------------------------------------------------------------

EXPECTED_PROVIDER_OS_SUPPORT: dict[str, set[str]] = {
    "mock-cloud": {"mockos-1.0-amd64", "mockos-1.0-arm64", "mockwin-1.0"},
    "mock-local": {"mockos-1.0-amd64", "mockos-1.0-arm64"},
}


def _provider_os_support() -> dict[str, set[str]]:
    support: dict[str, set[str]] = {}
    for plugin in PluginManifest.load_all("provider"):
        catalog = plugin.get("catalog")
        if not isinstance(catalog, dict):
            continue
        oses = catalog.get("oses")
        if not isinstance(oses, list):
            continue
        support[plugin["id"]] = {
            entry["id"]
            for entry in oses
            if isinstance(entry, dict) and entry.get("id")
        }
    return support


class TestProviderOsSupport:
    def test_every_provider_declares_catalog_oses(self) -> None:
        for plugin in PluginManifest.load_all("provider"):
            catalog = plugin.get("catalog")
            assert isinstance(catalog, dict), f"{plugin['id']}: missing catalog block"
            assert isinstance(catalog.get("oses"), list), f"{plugin['id']}: catalog.oses missing"

    def test_provider_os_support_matches_expected(self) -> None:
        support = _provider_os_support()
        for provider_id, expected_oses in EXPECTED_PROVIDER_OS_SUPPORT.items():
            assert provider_id in support, f"{provider_id} not in support map"
            assert support[provider_id] == expected_oses, (
                f"{provider_id}: expected {expected_oses}, got {support[provider_id]}"
            )

    def test_no_extra_providers_in_support_map(self) -> None:
        support = _provider_os_support()
        assert set(support.keys()) == set(EXPECTED_PROVIDER_OS_SUPPORT.keys())


# ---------------------------------------------------------------------------
# Aggregator reconstructs full OS rows
# ---------------------------------------------------------------------------


class TestAggregatedOsRows:
    def test_os_identity_rows_have_provider_image_fields(self) -> None:
        catalog = load_catalog()
        os_by_id = {entry["id"]: entry for entry in catalog["oses"]}

        # Identity fields come from _catalog-base; provider-specific image fields
        # are field-merged from each provider's catalog.oses contribution
        # (cloud_image_url from mock-cloud, vagrant_box from mock-local).
        ubuntu_amd = os_by_id["mockos-1.0-amd64"]
        assert ubuntu_amd["family"] == "ubuntu"
        assert ubuntu_amd["version"] == "1.0"
        assert ubuntu_amd["arch"] == "amd64"
        assert "cloud_image_url" in ubuntu_amd
        assert "vagrant_box" in ubuntu_amd

        ubuntu_arm = os_by_id["mockos-1.0-arm64"]
        assert ubuntu_arm["arch"] == "arm64"
        assert "cloud_image_url" in ubuntu_arm
        assert "vagrant_box" in ubuntu_arm

        windows = os_by_id["mockwin-1.0"]
        assert windows["family"] == "windows"
        assert "cloud_image_url" in windows


# ---------------------------------------------------------------------------
# Bundles relocated to package manifests
# ---------------------------------------------------------------------------


class TestBundlesRelocated:
    def test_all_bundles_present_in_aggregated_catalog(self) -> None:
        catalog = load_catalog()
        bundle_ids = {entry["id"] for entry in catalog["bundles"]}
        expected = {
            "mock-dev",
            "mock-gaming",
        }
        assert bundle_ids == expected

    def test_bundles_sourced_from_bundle_plugins(self) -> None:
        catalog = load_catalog()
        central_bundle_ids = {
            entry["id"] for entry in catalog["bundles"]
        }
        plugin_bundle_ids: set[str] = set()
        for plugin in PluginManifest.load_all("bundle"):
            if plugin.get("id"):
                plugin_bundle_ids.add(plugin["id"])
        assert central_bundle_ids == plugin_bundle_ids


# ---------------------------------------------------------------------------
# Machines relocated to provider manifests
# ---------------------------------------------------------------------------


class TestMachinesRelocated:
    def test_all_machines_present_in_aggregated_catalog(self) -> None:
        catalog = load_catalog()
        machine_names = {entry["name"] for entry in catalog["machines"]}
        expected = {
            "mock-small",
            "mock-gpu",
            "mock-vm",
        }
        assert machine_names == expected

    def test_machines_sourced_from_provider_manifests(self) -> None:
        provider_machine_names: set[str] = set()
        for plugin in PluginManifest.load_all("provider"):
            catalog = plugin.get("catalog")
            if not isinstance(catalog, dict):
                continue
            machines = catalog.get("machines")
            if not isinstance(machines, list):
                continue
            for machine in machines:
                if isinstance(machine, dict) and machine.get("name"):
                    provider_machine_names.add(machine["name"])
        catalog = load_catalog()
        catalog_machine_names = {entry["name"] for entry in catalog["machines"]}
        assert catalog_machine_names == provider_machine_names
