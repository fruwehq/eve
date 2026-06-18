"""read_resolved_from_env_or_stdin must not block on an interactive terminal."""

from __future__ import annotations

import pytest

from eve_sdk.dispatch import DispatchError, read_resolved_from_env_or_stdin


def test_tty_with_no_resolved_json_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVE_RESOLVED_JSON", raising=False)

    class _TTY:
        def isatty(self) -> bool:
            return True

        def read(self) -> str:  # pragma: no cover - must not be called
            raise AssertionError("stdin.read() must not be called on a TTY")

    monkeypatch.setattr("sys.stdin", _TTY())
    with pytest.raises(DispatchError, match="instance-scoped"):
        read_resolved_from_env_or_stdin()


def test_env_json_is_used_without_touching_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVE_RESOLVED_JSON", '{"instance": {"name": "x"}}')

    class _Boom:
        def isatty(self) -> bool:
            return True

        def read(self) -> str:  # pragma: no cover
            raise AssertionError("stdin must not be read when EVE_RESOLVED_JSON is set")

    monkeypatch.setattr("sys.stdin", _Boom())
    assert read_resolved_from_env_or_stdin()["instance"]["name"] == "x"
