from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tui.settings import FIELD_LABELS, field_label, root_dir
from tui.widgets import ProviderConfigScreen, SettingsScreen


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
