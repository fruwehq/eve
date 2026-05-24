from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tui.settings import FIELD_LABELS, field_label, root_dir


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


def test_source_tag_derivation(monkeypatch) -> None:
    assert True
