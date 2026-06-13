from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

import pytest

from eve_sdk.state import State


def _state_writer(state_dir: str, index: int) -> None:
    import os

    os.environ["EVE_STATE_DIR"] = state_dir
    State.record_operation(
        "concurrency-test",
        "provider.status",
        "succeeded" if index % 2 == 0 else "failed",
        error=f"writer {index} error" if index % 2 else None,
        provider_state="running" if index % 2 == 0 else "error",
    )


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


def test_state_concurrent_writers_preserve_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_STATE_DIR", str(tmp_path))
    State.write("concurrency-test", State.default_state("concurrency-test", "2026-01-01T00:00:00Z"))

    ctx = mp.get_context("spawn")
    writers = [ctx.Process(target=_state_writer, args=(str(tmp_path), index)) for index in range(20)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    assert all(writer.exitcode == 0 for writer in writers)
    state_path = tmp_path / "instances/concurrency-test.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    State.validate_state(state)
    assert len(state["operation_history"]) == 20
    assert {entry["status"] for entry in state["operation_history"]} == {"succeeded", "failed"}
