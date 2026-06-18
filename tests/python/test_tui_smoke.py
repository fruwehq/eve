"""Headless TUI smoke tests via Textual's run_test harness.

Mounts the real app + the plugin screen so CSS/compose errors are caught (the
pure-helper tests can't see these). Skips when Textual isn't installed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_PLUGIN_ROOTS", str(ROOT / "tests/fixtures/hermetic"))
    monkeypatch.setenv("EVE_PLUGIN_ROOTS_EXCLUSIVE", "1")
    monkeypatch.setenv("EVE_HOME", str(tmp_path))


def test_app_mounts_and_renders() -> None:
    from tui.app import EveTui

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query("#instances")
            assert app.query("#refresh")  # relocated refresh button exists

    asyncio.run(_run())


def test_plugin_screen_opens_and_lists_recommended() -> None:
    from textual.widgets import DataTable

    from tui.app import EveTui
    from tui.widgets import PluginSourcesScreen

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = PluginSourcesScreen()
            await app.push_screen(screen)
            await pilot.pause()
            # query the screen directly (an on-mount modal may sit on the stack)
            table = screen.query_one("#plugins-table", DataTable)
            assert table.row_count > 0  # recommended catalog is listed

    asyncio.run(_run())


def test_add_url_opens_prompt_modal() -> None:
    from textual.widgets import Button

    from tui.app import EveTui
    from tui.widgets import PluginSourcesScreen, TextPromptScreen

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = PluginSourcesScreen()
            await app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#plugins-add-url", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, TextPromptScreen)

    asyncio.run(_run())


def test_lists_bind_space_to_select() -> None:
    # ListTable maps space to the same select_cursor action as enter (DataTable's
    # enter binding), whose enter->focus-right-pane path is already exercised.
    from tui.app import EveTui, ListTable

    space = [b for b in ListTable.BINDINGS if getattr(b, "key", None) == "space"]
    assert space and space[0].action == "select_cursor"

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            for table_id in ("#instances", "#packages", "#bundles"):
                assert isinstance(app.query_one(table_id), ListTable)

    asyncio.run(_run())


def test_plugin_toggle_add_then_flips_to_remove() -> None:
    from textual.widgets import Button

    from tui import plugins as p
    from tui.app import EveTui
    from tui.widgets import PluginSourcesScreen

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = PluginSourcesScreen()
            await app.push_screen(screen)
            await pilot.pause()
            toggle = screen.query_one("#plugins-toggle", Button)
            assert str(toggle.label) == "Add selected"
            assert screen._rows[0][0] == "rec"  # empty override -> all recommended
            sid = screen._rows[0][1]
            screen._activate_current()  # space/enter/button on a recommended row -> add
            await pilot.pause()
            assert any(r["id"] == sid for r in p.configured_rows())
            # the added source is now configured at row 0 -> button flips
            assert str(toggle.label) == "Remove selected"

    asyncio.run(_run())


def test_new_instance_gated_when_no_platforms() -> None:
    from tui.app import EveTui
    from tui.widgets import NewInstanceScreen

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.catalog_options = {"providers": [], "platforms": [], "bundles": [], "packages": []}
            app.action_new_instance()  # should notify, not open the wizard
            await pilot.pause()
            assert not any(isinstance(s, NewInstanceScreen) for s in app.screen_stack)

    asyncio.run(_run())


def test_new_instance_highlight_guard_no_crash() -> None:
    # Empty platform table fires RowHighlighted(row_key=None) — must not crash.
    from tui.widgets import NewInstanceScreen

    screen = NewInstanceScreen({"providers": [], "platforms": [], "bundles": [], "packages": []})

    class _FakeTable:
        id = "platform-cards"

    class _FakeEvent:
        data_table = _FakeTable()
        row_key = None

    screen.on_data_table_row_highlighted(_FakeEvent())  # no exception
