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


def test_session_parses_once_across_mixed_ops() -> None:
    # The Phase 5 acceptance: an N-op session (the mix a TUI/batch run makes)
    # parses catalog + plugins exactly once.
    engine = Engine()
    engine.catalog_options()
    engine.plugin_list(kind="provider")
    engine.plugin_list(kind="package")
    for row in engine.instance_rows():
        engine.instance_view(row["name"])
    engine.instance_statuses()
    engine.instance_aggregate()
    assert catalog_mod.load_count() == 1
    assert pm.load_count() == 1


def test_instance_view_cold_equals_warm() -> None:
    import json
    import subprocess

    engine = Engine()
    rows = engine.instance_rows()
    if not rows:
        pytest.skip("no instances in registry")
    name = str(rows[0]["name"])
    result = subprocess.run(
        ["poetry", "run", "python", "scripts/instance-view", "--instance", name],
        capture_output=True,
        text=True,
        check=True,
    )
    assert engine.instance_view(name) == json.loads(result.stdout)


def test_instance_statuses_cold_equals_warm() -> None:
    # The --statuses path never parses catalog/plugins (a fast registry+state
    # sweep), so the warm Engine and the cold script must agree byte-for-byte.
    import json
    import subprocess

    engine = Engine()
    result = subprocess.run(
        ["poetry", "run", "python", "scripts/instance-view", "--statuses"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert engine.instance_statuses() == json.loads(result.stdout)["statuses"]
    # Statuses sweep must not bump either parse counter.
    assert catalog_mod.load_count() == 0
    assert pm.load_count() == 0


def test_tui_startup_parses_once() -> None:
    # The Phase 5 TUI acceptance: simulate the data calls a fresh TUI makes on
    # startup (catalog_options + provider_pane_data + provider capabilities +
    # instance list + statuses + aggregate + one instance_view) and assert that
    # the catalog and plugin manifests are parsed exactly once across all of it.
    #
    # These helpers are imported from the TUI package directly so the test
    # exercises the actual code path the TUI walks on startup.
    import tui.commands as tui_commands
    import tui.state as tui_state

    # Reset the per-process module-level capability cache so this test's first
    # call is the TUI's first call.
    tui_commands._provider_capabilities_cache = None

    tui_commands.catalog_options()
    tui_commands.provider_capabilities_map()
    tui_commands.provider_pane_data()
    tui_commands.instance_rows()
    tui_commands.instance_statuses()
    tui_state.aggregate_summary()
    rows = tui_commands.instance_rows()
    if rows:
        tui_commands.instance_view(str(rows[0]["name"]))

    assert catalog_mod.load_count() == 1
    assert pm.load_count() == 1


# --- batch mode: line->op translation (pure, no execution) ---------------- #

def test_parse_batch_line_splits_shell_style() -> None:
    import runpy

    cli = runpy.run_path("scripts/eve-cli")
    parse = cli["parse_batch_line"]

    assert parse("") == []
    assert parse("   ") == []
    assert parse("# a comment") == []
    assert parse("catalog list --json") == ["catalog", "list", "--json"]
    # shlex semantics: quoted args survive as one token.
    assert parse('instance view "name with spaces"') == ["instance", "view", "name with spaces"]
    # Inline comments after tokens are NOT stripped (shlex does not see # specially).
    assert parse("plugin list --kind provider") == ["plugin", "list", "--kind", "provider"]


def test_warm_batch_ops_table_covers_read_verbs() -> None:
    import runpy

    cli = runpy.run_path("scripts/eve-cli")
    warm = cli["_WARM_BATCH_OPS"]

    # Every read-only verb the TUI / scripted pipelines hammer lives here, so a
    # batch session serves them from the warm Engine rather than subprocessing.
    for expected in {("catalog", "list"), ("plugin", "list"), ("instance", "list"),
                     ("instance", "view"), ("instance", "statuses")}:
        assert expected in warm


def test_batch_session_parses_once() -> None:
    # An N-op batch through the warm Engine must parse catalog + plugins exactly
    # once. Read verbs dispatch in-process; the test does not execute mutating
    # verbs (no instance/cloud).
    import runpy

    cli = runpy.run_path("scripts/eve-cli")
    run_batch = cli["run_batch"]

    engine = Engine()
    rows = engine.instance_rows()
    instance_line = f"instance view {rows[0]['name']}" if rows else "instance statuses"
    ops = [
        "catalog list --json",
        "plugin list --kind provider",
        "plugin list --kind package",
        "instance list",
        "instance statuses",
        instance_line,
        "instance statuses",
        "# comment skipped",
        "",
    ]
    captured: list[str] = []
    code = run_batch(ops, engine=engine, out=captured.append)
    assert code == 0
    # The batch emitted one block of output per non-empty op.
    assert len(captured) >= 6
    assert catalog_mod.load_count() == 1
    assert pm.load_count() == 1
