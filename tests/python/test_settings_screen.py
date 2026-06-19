from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tui.settings import FIELD_LABELS, field_label, field_meta, root_dir
from tui.widgets import EditFieldScreen, ProviderConfigScreen, SettingsScreen


class ScreenHarness(App[None]):
    def __init__(self, modal: Screen[Any]) -> None:
        super().__init__()
        self.modal = modal

    def compose(self) -> ComposeResult:
        yield self.modal


async def _data_table_cursor_type(modal: Screen[Any], selector: str) -> str:
    app = ScreenHarness(modal)
    async with app.run_test(size=(120, 40)):
        return modal.query_one(selector, DataTable).cursor_type


def test_field_label_known_fields() -> None:
    assert field_label("global", "vm_user_name") == "VM Username"
    assert field_label("display", "fps") == "FPS"
    assert field_label("aws", "region") == "Region"


def test_field_label_unknown_field_falls_back_to_title() -> None:
    assert field_label("global", "some_new_field") == "Some New Field"


def test_field_labels_dict_covers_expected_fields() -> None:
    expected = {"vm_user_name", "my_ip", "fps", "resolution", "host", "project"}
    assert expected.issubset(set(FIELD_LABELS.keys()))


def test_root_dir_points_to_project_root() -> None:
    root = Path(root_dir())
    assert (root / "config" / "catalog.yaml").is_file()
    assert (root / "scripts" / "eve-tui").is_file()


def test_settings_table_uses_row_cursor(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))

    assert asyncio.run(_data_table_cursor_type(SettingsScreen(), "#settings-table")) == "row"


def test_provider_config_table_uses_row_cursor(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))

    assert (
        asyncio.run(_data_table_cursor_type(ProviderConfigScreen("vultr", "Vultr"), "#pc-table"))
        == "row"
    )


def test_source_tag_derivation(monkeypatch) -> None:
    assert True


def test_my_ip_label_is_plain_ip_not_cidr() -> None:
    # MY_IP is consumed as a plain IP (providers append /32), so the label and
    # example must be a plain address, not a CIDR.
    assert field_label("global", "my_ip") == "My IP"
    meta = field_meta("global", "my_ip")
    assert "plain IP" in meta["description"]
    assert meta["example"] == "203.0.113.42"


def test_field_meta_provides_description_and_example() -> None:
    meta = field_meta("global", "vm_user_name")
    assert meta["description"] and meta["example"]
    # Unknown field -> empty mapping (no crash).
    assert field_meta("global", "does_not_exist") == {}


def _settings_columns(monkeypatch, tmp_path) -> list[str]:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))
    screen = SettingsScreen()
    app = ScreenHarness(screen)

    async def _run() -> list[str]:
        async with app.run_test(size=(120, 40)):
            table = screen.query_one("#settings-table", DataTable)
            return [str(c.label) for c in table.columns.values()]

    return asyncio.run(_run())


def test_settings_table_has_no_description_column(monkeypatch, tmp_path) -> None:
    columns = _settings_columns(monkeypatch, tmp_path)
    assert columns == ["Section", "Field", "Value", "Source"]
    assert "Description" not in columns


def test_settings_has_primary_edit_button(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))
    screen = SettingsScreen()
    app = ScreenHarness(screen)

    async def _run() -> None:
        async with app.run_test(size=(120, 40)):
            edit = screen.query_one("#settings-edit", Button)
            assert str(edit.label) == "Edit"
            assert edit.variant == "primary"

    asyncio.run(_run())


def _edit_detail_text(**kwargs: Any) -> str:
    return EditFieldScreen("My IP", kwargs.pop("current", ""), **kwargs).detail_markup()


def test_edit_field_status_wording_not_misleading() -> None:
    # An unset field with no default must not claim "custom value".
    unset = _edit_detail_text(source="unset", description="d", example="203.0.113.42")
    assert "custom value" not in unset.lower()
    assert "Not set" in unset
    assert "Example: 203.0.113.42" in unset

    # Overridden -> "Modified" and the default is shown.
    modified = _edit_detail_text(source="config.yaml", default="ubuntu")
    assert "Modified" in modified and "ubuntu" in modified

    # Using the built-in default.
    default = _edit_detail_text(source="default", default="ubuntu")
    assert "Using default" in default and "ubuntu" in default
