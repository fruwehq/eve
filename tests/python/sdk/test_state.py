from __future__ import annotations

from pathlib import Path

import pytest

from eve_sdk.state import State


def test_state_read_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_STATE_DIR", str(tmp_path))

    assert State.read("demo")["provider_state"] == "unknown"


def test_state_record_operation_and_recover(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_STATE_DIR", str(tmp_path))

    State.record_operation("demo", "provider.up", "running", desired_state="running", provider_state="changing")
    recovered = State.recover_running("demo")

    assert recovered["provider_state"] == "error"
    assert recovered["last_operation"]["status"] == "failed"
    assert "Recovered interrupted operation provider.up" in recovered["last_error"]


def test_state_rejects_invalid_enum() -> None:
    with pytest.raises(ValueError, match="provider_state must be one of"):
        State.record_operation("demo", "provider.up", "succeeded", provider_state="bogus")
