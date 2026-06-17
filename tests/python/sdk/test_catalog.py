"""Unit tests for the catalog aggregator (``eve_sdk.catalog``).

Covers:
- ``merge_entries`` — whole-row replace keyed on id/name.
- ``merge_os_fields`` — field-level union keyed on id.
- ``aggregate`` — empty-contribution parity, provider catalog contributions,
  package bundle contributions, and central-doc overlay ordering.
"""

from __future__ import annotations

from typing import Any

from eve_sdk.catalog import (
    CATALOG_SECTIONS,
    aggregate,
    merge_entries,
    merge_os_fields,
)


# ---------------------------------------------------------------------------
# merge_entries (whole-row replace)
# ---------------------------------------------------------------------------


class TestMergeEntries:
    def test_append_new_entries(self) -> None:
        target: list[dict[str, Any]] = []
        merge_entries(target, [{"name": "a"}, {"name": "b"}], "name")
        assert target == [{"name": "a"}, {"name": "b"}]

    def test_replace_by_key(self) -> None:
        target: list[dict[str, Any]] = [{"name": "a", "v": 1}]
        merge_entries(target, [{"name": "a", "v": 2}], "name")
        assert target == [{"name": "a", "v": 2}]

    def test_preserve_order_on_replace(self) -> None:
        target: list[dict[str, Any]] = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        merge_entries(target, [{"name": "b", "v": 99}], "name")
        assert target == [{"name": "a"}, {"name": "b", "v": 99}, {"name": "c"}]

    def test_skip_empty_key(self) -> None:
        target: list[dict[str, Any]] = []
        merge_entries(target, [{"name": ""}], "name")
        assert target == []

    def test_skip_missing_key(self) -> None:
        target: list[dict[str, Any]] = []
        merge_entries(target, [{"other": 1}], "name")
        assert target == []

    def test_skip_non_dict_entries(self) -> None:
        target: list[dict[str, Any]] = []
        merge_entries(target, ["str", 42, None, {"name": "ok"}], "name")
        assert target == [{"name": "ok"}]

    def test_non_list_entries_ignored(self) -> None:
        target: list[dict[str, Any]] = [{"name": "a"}]
        merge_entries(target, "not-a-list", "name")  # type: ignore[arg-type]
        assert target == [{"name": "a"}]

    def test_empty_entries_noop(self) -> None:
        target: list[dict[str, Any]] = [{"name": "a"}]
        merge_entries(target, [], "name")
        assert target == [{"name": "a"}]


# ---------------------------------------------------------------------------
# merge_os_fields (field-level union)
# ---------------------------------------------------------------------------


class TestMergeOsFields:
    def test_append_new_entry(self) -> None:
        target: list[dict[str, Any]] = []
        merge_os_fields(target, [{"id": "os-1", "family": "ubuntu"}], "id")
        assert target == [{"id": "os-1", "family": "ubuntu"}]

    def test_field_level_union_combines_fields(self) -> None:
        target: list[dict[str, Any]] = [
            {"id": "os-1", "family": "ubuntu", "version": "26.04"}
        ]
        merge_os_fields(target, [{"id": "os-1", "aws_ami_name_pattern": "ubuntu-*"}], "id")
        assert target == [
            {
                "id": "os-1",
                "family": "ubuntu",
                "version": "26.04",
                "aws_ami_name_pattern": "ubuntu-*",
            }
        ]

    def test_field_level_overrides_existing_value(self) -> None:
        target: list[dict[str, Any]] = [
            {"id": "os-1", "family": "ubuntu", "version": "26.04"}
        ]
        merge_os_fields(target, [{"id": "os-1", "version": "24.04"}], "id")
        assert target == [{"id": "os-1", "family": "ubuntu", "version": "24.04"}]

    def test_multiple_providers_combine_fields(self) -> None:
        target: list[dict[str, Any]] = [
            {"id": "os-1", "family": "ubuntu", "version": "26.04", "arch": "amd64"}
        ]
        merge_os_fields(target, [{"id": "os-1", "aws_ami_name_pattern": "ubuntu-*"}], "id")
        merge_os_fields(
            target,
            [{"id": "os-1", "gcp_image_project": "ubuntu-os-cloud", "gcp_image_family": "ubuntu-2604-lts-amd64"}],
            "id",
        )
        assert target == [
            {
                "id": "os-1",
                "family": "ubuntu",
                "version": "26.04",
                "arch": "amd64",
                "aws_ami_name_pattern": "ubuntu-*",
                "gcp_image_project": "ubuntu-os-cloud",
                "gcp_image_family": "ubuntu-2604-lts-amd64",
            }
        ]

    def test_new_entry_is_copied(self) -> None:
        original = {"id": "os-1", "family": "ubuntu"}
        target: list[dict[str, Any]] = []
        merge_os_fields(target, [original], "id")
        assert target == [original]
        target[0]["family"] = "debian"
        assert original["family"] == "ubuntu"

    def test_skip_empty_id(self) -> None:
        target: list[dict[str, Any]] = []
        merge_os_fields(target, [{"id": ""}], "id")
        assert target == []

    def test_skip_non_dict_entries(self) -> None:
        target: list[dict[str, Any]] = []
        merge_os_fields(target, ["str", 42, {"id": "ok"}], "id")
        assert target == [{"id": "ok"}]

    def test_non_list_entries_ignored(self) -> None:
        target: list[dict[str, Any]] = [{"id": "a"}]
        merge_os_fields(target, None, "id")
        assert target == [{"id": "a"}]


# ---------------------------------------------------------------------------
# aggregate — empty-contribution parity
# ---------------------------------------------------------------------------


class TestAggregateParity:
    """When plugin contributions are empty, the aggregator output must equal the
    central catalog load exactly."""

    def test_empty_contributions_equals_central(self) -> None:
        central = {
            "bundles": [{"id": "b1", "includes": ["p1"]}],
            "inits": [{"id": "i1", "os_family": "ubuntu"}],
            "locations": [{"name": "tokyo"}],
            "machines": [{"name": "m1", "kind": "vm"}],
            "oses": [{"id": "os-1", "family": "ubuntu", "version": "26.04"}],
            "packages": [{"id": "p1"}],
        }
        result = aggregate([central], [])
        for section in CATALOG_SECTIONS:
            assert result[section] == central[section]

    def test_empty_inputs_produces_all_sections(self) -> None:
        result = aggregate([], [])
        assert set(result.keys()) == set(CATALOG_SECTIONS.keys())
        for section in CATALOG_SECTIONS:
            assert result[section] == []

    def test_plugin_without_catalog_is_noop(self) -> None:
        central = {"machines": [{"name": "m1"}]}
        plugin = {"kind": "provider"}
        result = aggregate([central], [plugin])
        assert result["machines"] == [{"name": "m1"}]

    def test_package_without_bundles_is_noop(self) -> None:
        central = {"bundles": [{"id": "b1", "includes": ["p1"]}]}
        plugin = {"kind": "package"}
        result = aggregate([central], [plugin])
        assert result["bundles"] == [{"id": "b1", "includes": ["p1"]}]


# ---------------------------------------------------------------------------
# aggregate — provider catalog contributions
# ---------------------------------------------------------------------------


class TestAggregateProviderContributions:
    def test_provider_machine_appended(self) -> None:
        central = {"machines": [{"name": "m1"}]}
        plugin = {"kind": "provider", "catalog": {"machines": [{"name": "m2"}]}}
        result = aggregate([central], [plugin])
        assert result["machines"] == [{"name": "m1"}, {"name": "m2"}]

    def test_provider_machine_replaces_same_key(self) -> None:
        central = {"machines": [{"name": "m1", "defaults": {"x": 1}}]}
        plugin = {"kind": "provider", "catalog": {"machines": [{"name": "m1", "defaults": {"x": 2}}]}}
        result = aggregate([central], [plugin])
        assert result["machines"] == [{"name": "m1", "defaults": {"x": 2}}]

    def test_provider_os_field_level_merge(self) -> None:
        central = {"oses": [{"id": "os-1", "family": "ubuntu", "version": "26.04"}]}
        plugin = {"kind": "provider", "catalog": {"oses": [{"id": "os-1", "aws_ami_name_pattern": "ubuntu-*"}]}}
        result = aggregate([central], [plugin])
        assert result["oses"] == [
            {
                "id": "os-1",
                "family": "ubuntu",
                "version": "26.04",
                "aws_ami_name_pattern": "ubuntu-*",
            }
        ]

    def test_multiple_providers_os_fields_combine(self) -> None:
        central = {"oses": [{"id": "os-1", "family": "ubuntu"}]}
        aws = {
            "kind": "provider",
            "catalog": {"oses": [{"id": "os-1", "aws_ami_name_pattern": "ubuntu-*"}]},
        }
        gcp = {
            "kind": "provider",
            "catalog": {
                "oses": [
                    {"id": "os-1", "gcp_image_project": "ubuntu-os-cloud", "gcp_image_family": "ubuntu-2604-lts-amd64"}
                ]
            },
        }
        result = aggregate([central], [aws, gcp])
        assert result["oses"] == [
            {
                "id": "os-1",
                "family": "ubuntu",
                "aws_ami_name_pattern": "ubuntu-*",
                "gcp_image_project": "ubuntu-os-cloud",
                "gcp_image_family": "ubuntu-2604-lts-amd64",
            }
        ]

    def test_provider_init_contribution(self) -> None:
        central = {"inits": [{"id": "i1"}]}
        plugin = {"kind": "provider", "catalog": {"inits": [{"id": "i2"}]}}
        result = aggregate([central], [plugin])
        assert result["inits"] == [{"id": "i1"}, {"id": "i2"}]

    def test_provider_init_replaces_same_key(self) -> None:
        central = {"inits": [{"id": "i1", "os_family": "ubuntu"}]}
        plugin = {"kind": "provider", "catalog": {"inits": [{"id": "i1", "os_family": "windows"}]}}
        result = aggregate([central], [plugin])
        assert result["inits"] == [{"id": "i1", "os_family": "windows"}]


# ---------------------------------------------------------------------------
# aggregate — package bundle contributions
# ---------------------------------------------------------------------------


class TestAggregatePackageBundles:
    def test_package_bundles_appended(self) -> None:
        central = {"bundles": [{"id": "b1", "includes": ["p1"]}]}
        plugin = {"kind": "package", "bundles": [{"id": "b2", "includes": ["p2"]}]}
        result = aggregate([central], [plugin])
        assert result["bundles"] == [
            {"id": "b1", "includes": ["p1"]},
            {"id": "b2", "includes": ["p2"]},
        ]

    def test_package_bundle_replaces_same_id(self) -> None:
        central = {"bundles": [{"id": "b1", "includes": ["p1"]}]}
        plugin = {"kind": "package", "bundles": [{"id": "b1", "includes": ["p2", "p3"]}]}
        result = aggregate([central], [plugin])
        assert result["bundles"] == [{"id": "b1", "includes": ["p2", "p3"]}]


# ---------------------------------------------------------------------------
# aggregate — central doc overlay ordering
# ---------------------------------------------------------------------------


class TestAggregateCentralOverlay:
    def test_second_doc_overlays_first(self) -> None:
        base = {"machines": [{"name": "m1", "defaults": {"x": 1}}]}
        overlay = {"machines": [{"name": "m1", "defaults": {"x": 2}}]}
        result = aggregate([base, overlay], [])
        assert result["machines"] == [{"name": "m1", "defaults": {"x": 2}}]

    def test_second_doc_appends_new_entries(self) -> None:
        base = {"machines": [{"name": "m1"}]}
        overlay = {"machines": [{"name": "m2"}]}
        result = aggregate([base, overlay], [])
        assert result["machines"] == [{"name": "m1"}, {"name": "m2"}]

    def test_central_overlay_oses_field_level(self) -> None:
        base = {"oses": [{"id": "os-1", "family": "ubuntu", "version": "26.04"}]}
        overlay = {"oses": [{"id": "os-1", "cloud_image_url": "https://example.com/img.img"}]}
        result = aggregate([base, overlay], [])
        assert result["oses"] == [
            {
                "id": "os-1",
                "family": "ubuntu",
                "version": "26.04",
                "cloud_image_url": "https://example.com/img.img",
            }
        ]
