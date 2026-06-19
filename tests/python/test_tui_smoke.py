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


def test_footer_bindings_are_app_level_only() -> None:
    # Instance-lifecycle hotkeys were removed; Plugins moved g -> p; ?/help gone.
    from tui.app import EveTui

    by_key = {b.key: b.action for b in EveTui.BINDINGS}
    assert by_key.get("p") == "open_plugins"
    for removed in ("g", "?", "u", "t", "x", "d", "l"):
        assert removed not in by_key, f"binding {removed!r} should be removed"
    assert by_key.get("s") == "open_settings"
    assert by_key.get("r") == "queue_refresh"
    assert by_key.get("q") == "quit"


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


def test_new_instance_defaults_location_for_provider() -> None:
    # Post-WS3 the wizard picks no location from the platform row; it defaults to
    # a catalog location that serves the chosen provider so create gets a location.
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    screen = NewInstanceScreen(catalog_options())
    assert screen._default_location("mock-cloud") == "mock-tokyo"
    assert screen._default_location("does-not-exist") == ""


def test_new_instance_package_highlight_does_not_select_space_toggles() -> None:
    from textual.widgets import DataTable

    from tui.app import EveTui
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    async def _run() -> None:
        app = EveTui()
        screen = NewInstanceScreen(catalog_options())
        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()
            screen.set_step(2)
            await pilot.pause()
            table = screen.query_one("#package-select", DataTable)
            table.focus()
            table.move_cursor(row=1, column=0, animate=False)
            await pilot.pause()
            assert screen.highlighted_package_id
            assert screen.selected_package_ids == set()
            await pilot.press("space")
            await pilot.pause()
            assert screen.selected_package_ids == {screen.highlighted_package_id}

    asyncio.run(_run())


def test_new_instance_unsupported_package_highlightable_not_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    from textual.widgets import DataTable

    from tui.app import EveTui
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    notifications: list[str] = []

    async def _run() -> None:
        app = EveTui()
        screen = NewInstanceScreen(catalog_options())
        monkeypatch.setattr(screen, "notify", lambda message, **_: notifications.append(str(message)))
        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()
            screen.set_step(2)
            await pilot.pause()
            table = screen.query_one("#package-select", DataTable)
            unsupported = next(package for package in screen.package_ids if screen.package_select_reason(package))
            table.focus()
            table.move_cursor(row=screen.package_ids.index(unsupported), column=0, animate=False)
            await pilot.pause()
            assert screen.highlighted_package_id == unsupported
            await pilot.press("space")
            await pilot.pause()
            assert unsupported not in screen.selected_package_ids
            assert notifications

    asyncio.run(_run())


def test_new_instance_has_resources_step_with_prefilled_defaults() -> None:
    from textual.widgets import Button, Input

    from tui.app import EveTui
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    async def _run() -> None:
        app = EveTui()
        screen = NewInstanceScreen(catalog_options())
        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()
            assert "5 Review" in screen.wizard_step_label()
            screen.set_step(3)
            await pilot.pause()
            defaults = screen.selected_platform().get("defaults", {})
            assert screen.query_one("#new-disk", Input).value == str(defaults["disk_gb"])
            assert screen.query_one("#new-memory", Input).value == str(defaults["memory_mb"])
            assert screen.query_one("#next", Button).display is True
            assert screen.query_one("#create", Button).display is False
            screen.set_step(4)
            await pilot.pause()
            assert screen.query_one("#next", Button).display is False
            assert screen.query_one("#create", Button).display is True

    asyncio.run(_run())


def test_new_instance_resource_prefill_not_marked_touched_user_edit_is() -> None:
    # The prefill's own write must NOT mark the field touched (otherwise a later
    # platform change can't refresh the default); a real keystroke must.
    from textual.widgets import Input

    from tui.app import EveTui
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    async def _run() -> None:
        app = EveTui()
        screen = NewInstanceScreen(catalog_options())
        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()
            screen.set_step(3)
            await pilot.pause()
            assert screen._disk_touched is False
            assert screen._memory_touched is False
            disk = screen.query_one("#new-disk", Input)
            disk.focus()
            await pilot.press("9")
            await pilot.pause()
            assert screen._disk_touched is True

    asyncio.run(_run())


def test_new_instance_detail_panels_update_on_highlight() -> None:
    from textual.widgets import DataTable, Static

    from tui.app import EveTui
    from tui.commands import catalog_options
    from tui.widgets import NewInstanceScreen

    async def _run() -> None:
        app = EveTui()
        screen = NewInstanceScreen(catalog_options())
        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()
            screen.set_step(2)
            await pilot.pause()
            bundle_detail = screen.query_one("#bundle-detail", Static)
            package_detail = screen.query_one("#package-detail", Static)
            assert str(bundle_detail.render())
            assert str(package_detail.render())
            package_table = screen.query_one("#package-select", DataTable)
            before = str(package_detail.render())
            package_table.move_cursor(row=1, column=0, animate=False)
            await pilot.pause()
            assert str(package_detail.render()) != before

    asyncio.run(_run())


def test_delete_confirm_defaults_and_result() -> None:
    from textual.widgets import Button, Checkbox

    from tui.app import EveTui
    from tui.widgets import DeleteConfirmScreen

    captured: dict[str, object] = {}

    async def _run() -> None:
        app = EveTui()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = DeleteConfirmScreen("foo")
            await app.push_screen(screen, lambda r: captured.update(r or {}))
            await pilot.pause()
            # purge is OFF by default; down-first is a new opt-in option
            assert screen.query_one("#delete-purge", Checkbox).value is False
            assert screen.query_one("#delete-down", Checkbox).value is False
            screen.query_one("#delete-down", Checkbox).value = True
            screen.query_one("#confirm", Button).press()
            await pilot.pause()

    asyncio.run(_run())
    assert captured == {"confirmed": True, "down": True, "purge": False, "force": False}
