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


def test_derive_id_strips_git_suffix() -> None:
    assert plugins._derive_id("https://github.com/you/your-plugins.git") == "your-plugins"
    assert plugins._derive_id("../eve-providers") == "eve-providers"
