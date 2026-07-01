"""FSM platform (eve_sdk.fsm.EveFsm) over the harel engine.

Proves the v4.5 N/O invariant on a synthetic provider machine: `configured` and
`reachable` are FSM-computed from context that comes from *one* resolver, and a
settings change re-derives state. No real secrets/config on disk — the resolver is
injected (as the real platform will inject the shared ConfigEnv+secrets resolver).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# The harel engine is a new dependency; until it is pinned in pyproject (gated on a
# harel-python release tag), skip cleanly where it isn't installed so CI stays green.
pytest.importorskip("harel")

from eve_sdk.fsm import EveFsm  # noqa: E402  (must follow importorskip)

FIXTURE = Path(__file__).parent / "fsm_fixtures" / "provider.yaml"


def _make(settings: dict[str, str]) -> tuple[EveFsm, dict[str, dict[str, str]]]:
    holder = {"cur": dict(settings)}

    def resolve(scope: str, key: str, names: list[str]) -> dict[str, Any]:
        return {name: holder["cur"].get(name, "") for name in names}

    fsm = EveFsm(resolve)
    fsm.load("provider", FIXTURE.read_text())
    return fsm, holder


def _leaves(fsm: EveFsm) -> list[str]:
    return list(fsm.instance("provider", "vultr").active_leaf_names())


def test_unconfigured_without_secret() -> None:
    fsm, _ = _make({"api_key": "", "region": "ewr"})
    fsm.fire("provider", "vultr", "resolve")
    assert _leaves(fsm) == ["unconfigured"]


def test_configured_then_reachable_via_probe() -> None:
    fsm, _ = _make({"api_key": "KEY", "region": "ewr"})
    fsm.fire("provider", "vultr", "resolve")
    assert _leaves(fsm) == ["unreachable"]  # configured, not yet probed
    assert fsm.context("provider", "vultr")["region"] == "ewr"

    fsm.fire("provider", "vultr", "probe_ok")
    assert _leaves(fsm) == ["reachable"]
    assert fsm.view("provider", "vultr")["status"] == "active"


def test_settings_change_reevaluates() -> None:
    fsm, holder = _make({"api_key": "KEY", "region": "ewr"})
    fsm.fire("provider", "vultr", "resolve")
    fsm.fire("provider", "vultr", "probe_ok")
    assert _leaves(fsm) == ["reachable"]

    # secret removed at the source -> refresh delivers `env`, machine adopts it,
    # re-resolve derives `unconfigured`. Status and dispatch cannot disagree because
    # both read this same context.
    holder["cur"]["api_key"] = ""
    changed = fsm.refresh("provider", "vultr")
    assert changed == {"api_key": ""}
    fsm.fire("provider", "vultr", "resolve")
    assert _leaves(fsm) == ["unconfigured"]
