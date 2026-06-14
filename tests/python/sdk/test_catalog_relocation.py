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
    "aws": {"ubuntu-26.04-amd64", "windows-server-2025"},
    "gcp": {"ubuntu-26.04-amd64"},
    "local-qemu": {"ubuntu-26.04-amd64", "ubuntu-26.04-arm64"},
    "raspberry-pi": {"ubuntu-26.04-arm64"},
    "truenas": {"ubuntu-26.04-amd64", "ubuntu-26.04-arm64"},
    "vultr": {"windows-server-2025"},
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

        ubuntu_amd = os_by_id["ubuntu-26.04-amd64"]
        assert ubuntu_amd["family"] == "ubuntu"
        assert ubuntu_amd["version"] == "26.04"
        assert ubuntu_amd["arch"] == "amd64"
        assert "aws_ami_name_pattern" in ubuntu_amd
        assert "gcp_image_project" in ubuntu_amd
        assert "gcp_image_family" in ubuntu_amd
        assert "cloud_image_url" in ubuntu_amd
        assert "vagrant_box" in ubuntu_amd

        ubuntu_arm = os_by_id["ubuntu-26.04-arm64"]
        assert ubuntu_arm["arch"] == "arm64"
        assert "cloud_image_url" in ubuntu_arm
        assert "cloud_image_sha256" in ubuntu_arm
        assert "metal_image" in ubuntu_arm

        windows = os_by_id["windows-server-2025"]
        assert windows["family"] == "windows"
        assert "aws_ami_name_pattern" in windows
        assert "vultr_os_id" in windows


# ---------------------------------------------------------------------------
# Bundles relocated to package manifests
# ---------------------------------------------------------------------------


class TestBundlesRelocated:
    def test_all_bundles_present_in_aggregated_catalog(self) -> None:
        catalog = load_catalog()
        bundle_ids = {entry["id"] for entry in catalog["bundles"]}
        expected = {
            "desktop-gnome",
            "desktop-gnome-headless",
            "desktop-gnome-mac",
            "desktop-kde",
            "desktop-kde-headless",
            "desktop-streaming",
            "desktop-xfce",
            "desktop-xfce-headless",
            "dev-ai",
            "gaming-streaming",
            "remote-xpra",
        }
        assert bundle_ids == expected

    def test_bundles_sourced_from_package_manifests(self) -> None:
        catalog = load_catalog()
        central_bundle_ids = {
            entry["id"] for entry in catalog["bundles"]
        }
        package_bundle_ids: set[str] = set()
        for plugin in PluginManifest.load_all("package"):
            bundles = plugin.get("bundles")
            if not isinstance(bundles, list):
                continue
            for bundle in bundles:
                if isinstance(bundle, dict) and bundle.get("id"):
                    package_bundle_ids.add(bundle["id"])
        assert central_bundle_ids == package_bundle_ids


# ---------------------------------------------------------------------------
# Machines relocated to provider manifests
# ---------------------------------------------------------------------------


class TestMachinesRelocated:
    def test_all_machines_present_in_aggregated_catalog(self) -> None:
        catalog = load_catalog()
        machine_names = {entry["name"] for entry in catalog["machines"]}
        expected = {
            "aws-cheap-x86",
            "aws-gpu-g4dn-spot",
            "aws-gpu-g5",
            "gcp-cheap-x86",
            "local-qemu-medium",
            "raspberry-pi-5",
            "truenas-scale-medium",
            "vultr-vcg-a40-1c",
            "vultr-vcg-a40-2c",
            "vultr-vcg-a40-4c",
            "vultr-vcg-a40-6c",
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
