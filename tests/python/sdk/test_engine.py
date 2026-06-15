"""Tests for the warm execution Engine (``eve_sdk.engine``).

The Phase 5 invariant: a single Engine parses the catalog and plugin manifests
**once** and reuses them across many operations, instead of the cold per-op
re-parse the scripts pay. These tests assert that against the disk-parse counters
in ``eve_sdk.catalog`` and ``eve_sdk.plugin_manifest``, plus the fingerprint-based
cache invalidation.
"""

from __future__ import annotations

import pytest

from eve_sdk import catalog as catalog_mod
from eve_sdk import plugin_manifest as pm
from eve_sdk.engine import Engine, default_engine


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    pm.reset_load_count()
    catalog_mod.reset_load_count()


def test_plugins_parse_once_across_many_calls() -> None:
    engine = Engine()
    for _ in range(5):
        engine.plugins()
    assert pm.load_count() == 1


def test_catalog_parse_once_across_many_calls() -> None:
    engine = Engine()
    for _ in range(5):
        engine.catalog()
    # catalog aggregated once; manifests parsed once (reused for the catalog).
    assert catalog_mod.load_count() == 1
    assert pm.load_count() == 1


def test_catalog_reuses_memoized_plugins() -> None:
    engine = Engine()
    engine.plugins()
    engine.catalog()
    # The catalog must not trigger a second manifest parse.
    assert pm.load_count() == 1


def test_kind_filter_does_not_reparse() -> None:
    engine = Engine()
    providers = engine.plugins(kind="provider")
    packages = engine.plugins(kind="package")
    assert pm.load_count() == 1
    assert all(p["kind"] == "provider" for p in providers)
    assert all(p["kind"] == "package" for p in packages)


def test_reload_forces_reparse() -> None:
    engine = Engine()
    engine.plugins()
    engine.catalog()
    assert pm.load_count() == 1
    engine.reload()
    engine.plugins()
    assert pm.load_count() == 2


def test_fingerprint_change_invalidates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = Engine()
    monkeypatch.setattr(pm.PluginManifest, "fingerprint", classmethod(lambda cls: (("a", 1),)))
    engine.plugins()
    assert pm.load_count() == 1
    # Same fingerprint → still cached.
    engine.plugins()
    assert pm.load_count() == 1
    # Fingerprint drifts (e.g. `eve pull` ran) → cache invalidated, re-parse.
    monkeypatch.setattr(pm.PluginManifest, "fingerprint", classmethod(lambda cls: (("a", 2),)))
    engine.plugins()
    assert pm.load_count() == 2


def test_default_engine_is_shared() -> None:
    assert default_engine() is default_engine()


def test_catalog_options_parses_once() -> None:
    engine = Engine()
    for _ in range(3):
        engine.catalog_options()
    assert catalog_mod.load_count() == 1
    assert pm.load_count() == 1


def test_catalog_options_matches_cold_assembly() -> None:
    # The Engine view must equal the cold path's assembly exactly (same inputs,
    # same shared builder), guaranteeing parity with `catalog-options --json`.
    from eve_sdk.catalog import load_catalog
    from eve_sdk.catalog_view import build_catalog_options
    from eve_sdk.plugin_manifest import PluginManifest

    cold = build_catalog_options(
        load_catalog(),
        PluginManifest.load_all("provider"),
        PluginManifest.load_all("package"),
    )
    assert Engine().catalog_options() == cold


def test_plugin_list_matches_public_projection() -> None:
    from eve_sdk.plugin_manifest import PluginManifest

    engine = Engine()
    expected = [PluginManifest.public(p) for p in PluginManifest.load_all("provider")]
    assert engine.plugin_list(kind="provider") == expected


def test_plugin_list_parses_once() -> None:
    engine = Engine()
    engine.plugin_list(kind="provider")
    engine.plugin_list(kind="package")
    engine.plugin_list()
    assert pm.load_count() == 1
