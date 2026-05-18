from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tui.render import (
    command_label,
    display_state,
    format_aggregate,
    glyph_for_status,
    markup_for_status,
    package_source_label,
    package_summary_label,
    plain_log_line,
)
from tui.state import action_allowed_for_instance, password_supported, provider_actions_available, status_instance_name


def test_render_helpers_preserve_existing_labels() -> None:
    assert command_label(["make", "ssh", "INSTANCE=dev a"]) == "make ssh 'INSTANCE=dev a'"
    assert glyph_for_status("running") == "●"
    assert glyph_for_status("stopped") == "○"
    assert glyph_for_status("failed") == "!"
    assert glyph_for_status("unexpected") == "?"
    assert markup_for_status("running") == "[success]running[/]"
    assert markup_for_status("stopped") == "[warning]stopped[/]"
    assert display_state("unknown") == "new"
    assert plain_log_line("[success]done[/] [dim]now[/]") == "done now"


def test_package_summary_and_source_labels() -> None:
    assert package_source_label([]) == "available"
    assert package_source_label(["direct"]) == "extra"
    assert package_source_label(["bundle:desktop-streaming"]) == "bundle: desktop-streaming"
    assert package_summary_label({"installed": 2, "failed": 1}) == "1 failed / 2 installed"
    assert package_summary_label({}) == "none selected"


def test_state_helpers_preserve_existing_predicates(monkeypatch) -> None:
    status = {
        "instance": {
            "name": "win-a",
            "provider": "vultr",
            "os_family": "windows",
        }
    }
    assert status_instance_name(status) == "win-a"
    assert provider_actions_available({"provider_actions_available": True})
    assert action_allowed_for_instance({}, "steam", "windows")

    monkeypatch.setenv("EPHEMERAL_WINDOWS_PASSWORD", "secret")
    assert password_supported(status)
    monkeypatch.delenv("EPHEMERAL_WINDOWS_PASSWORD")
