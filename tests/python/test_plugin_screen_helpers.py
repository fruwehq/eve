"""Pure-helper tests for the TUI plugin-source screen (no Textual import)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tui import plugins


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Override lives at EVE_HOME/.eve/plugin-sources.yaml; the committed default
    # (config/plugin-sources.yaml) ships empty, so configured starts empty.
    monkeypatch.setenv("EVE_HOME", str(tmp_path))


def test_recommended_rows_lists_catalog() -> None:
    rows = plugins.recommended_rows()
    ids = {row["id"] for row in rows}
    assert {"eve-providers", "eve-packages-linux", "eve-plugins-ai"} <= ids
    assert all(row["added"] is False for row in rows)


def test_configured_starts_empty() -> None:
    assert plugins.configured_rows() == []


def test_add_recommended_then_configured_and_flagged() -> None:
    ok, _ = plugins.add_recommended("eve-providers")
    assert ok
    configured = plugins.configured_rows()
    assert [row["id"] for row in configured] == ["eve-providers"]
    rec = {row["id"]: row for row in plugins.recommended_rows()}
    assert rec["eve-providers"]["added"] is True


def test_add_recommended_unknown_fails() -> None:
    ok, msg = plugins.add_recommended("does-not-exist")
    assert not ok
    assert "unknown recommended id" in msg


def test_add_url_requires_ref_by_default() -> None:
    ok, msg = plugins.add_url("https://example.com/x.git")
    assert not ok
    assert "missing ref" in msg


def test_add_url_and_remove_roundtrip() -> None:
    ok, _ = plugins.add_url("https://example.com/x.git", ref="v1.0.0")
    assert ok
    assert [row["id"] for row in plugins.configured_rows()] == ["x"]
    ok, _ = plugins.remove("x")
    assert ok
    assert plugins.configured_rows() == []
    ok, msg = plugins.remove("x")
    assert not ok
    assert "no such source" in msg


def test_add_url_with_folder_roundtrips_into_override() -> None:
    ok, _ = plugins.add_url("https://example.com/x.git", ref="v1.0.0", subdir="providers")
    assert ok
    (row,) = plugins.configured_rows()
    assert row["id"] == "x"
    assert row["subdir"] == "providers"


def test_add_url_rejects_unsafe_folder_via_registry_validation() -> None:
    # The TUI does not re-implement the .. check — registry.parse_sources does.
    ok, msg = plugins.add_url("https://example.com/x.git", ref="v1.0.0", subdir="../escape")
    assert not ok
    assert "relative path inside" in msg


def test_is_local_folder() -> None:
    assert plugins.is_local_folder("../eve-providers")
    assert plugins.is_local_folder("/home/chris/eve-providers")
    assert not plugins.is_local_folder("https://github.com/fruwehq/eve-providers.git")
    assert not plugins.is_local_folder("git@github.com:fruwehq/eve-providers.git")


def test_configured_row_returns_local_flag() -> None:
    ok, _ = plugins.add_url("../eve-providers", ref="v4.5", auth="none")
    assert ok
    row = plugins.configured_row("eve-providers")
    assert row is not None
    assert row["local"] is True
    assert row["url"] == "../eve-providers"

    ok2, _ = plugins.add_url("https://example.com/x.git", ref="v1.0.0")
    assert ok2
    row2 = plugins.configured_row("x")
    assert row2 is not None
    assert row2["local"] is False


def test_update_source_replaces_by_id() -> None:
    ok, _ = plugins.add_url("https://example.com/x.git", ref="v1.0.0")
    assert ok
    ok2, msg = plugins.update_source("x", url="../local-x", ref="v2.0.0", subdir="sub")
    assert ok2
    row = plugins.configured_row("x")
    assert row["url"] == "../local-x"
    assert row["ref"] == "v2.0.0"
    assert row["subdir"] == "sub"
    assert row["local"] is True


def test_configured_row_returns_none_for_missing() -> None:
    assert plugins.configured_row("nonexistent") is None


def test_derive_id_strips_git_suffix() -> None:
    assert plugins._derive_id("https://github.com/you/your-plugins.git") == "your-plugins"
    assert plugins._derive_id("../eve-providers") == "eve-providers"
