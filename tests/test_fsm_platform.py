"""FSM platform (eve_sdk.fsm.EveFsm) over the harel engine.

Proves the v4.5 N/O invariant on a synthetic provider machine: `configured` and
`reachable` are FSM-computed from context that comes from *one* resolver, and a
settings change re-derives state. No real secrets/config on disk — the resolver is
injected (as the real platform will inject the shared ConfigEnv+secrets resolver).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

# The statechart engine (being renamed harel -> determa-state) is a new dependency;
# until it is pinned in pyproject, skip cleanly where neither package is installed so
# CI stays green.
if not any(importlib.util.find_spec(name) for name in ("determa_state", "harel")):
    pytest.skip("determa-state/harel engine not installed", allow_module_level=True)

from eve_sdk.fsm import EveFsm

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


def test_provider_context_resolver_uses_shared_config_secret_path(monkeypatch: Any) -> None:
    """The real resolver reads settings + secrets from the same path dispatch uses."""
    from eve_sdk.fsm import provider_context_resolver

    monkeypatch.setattr(
        "eve_sdk.config.ConfigEnv.environment",
        classmethod(lambda cls, *a, **k: {"VULTR_REGION": "ewr"}),
    )
    monkeypatch.setattr(
        "eve_sdk.provider_command._load_public_plugin",
        lambda kind, plugin_id: {
            "id": plugin_id,
            "kind": "provider",
            "config_schema": {"secrets": {"api_key": {"env_var": "VULTR_API_KEY"}}},
        },
    )
    monkeypatch.setattr("eve_sdk.provider_command.Secrets.read", staticmethod(lambda name: {"api_key": "SECRET"}))

    resolve = provider_context_resolver()
    got = resolve("provider", "vultr", ["VULTR_API_KEY", "VULTR_REGION"])
    assert got == {"VULTR_API_KEY": "SECRET", "VULTR_REGION": "ewr"}


def test_core_provider_machine_configured_from_required_secret(monkeypatch: Any) -> None:
    """The core provider machine: configured = a required secret is eve-resolved; a
    connectivity probe promotes it to reachable. Exercises core/fsm/provider.yaml."""
    from eve_sdk.fsm import EveFsm, provider_configured_resolver

    monkeypatch.setattr("eve_sdk.config.ConfigEnv.environment", classmethod(lambda cls, *a, **k: {}))
    monkeypatch.setattr(
        "eve_sdk.provider_command._load_public_plugin",
        lambda kind, plugin_id: {
            "id": plugin_id,
            "kind": "provider",
            "config_schema": {"secrets": {"api_key": {"required": True, "env_var": "VULTR_API_KEY"}}},
        },
    )
    box = {"secrets": {}}
    monkeypatch.setattr("eve_sdk.provider_command.Secrets.read", staticmethod(lambda name: dict(box["secrets"])))

    fsm = EveFsm(provider_configured_resolver())
    core = (Path(__file__).resolve().parents[1] / "core" / "fsm" / "provider.yaml").read_text()
    fsm.load("provider", core)

    # no secret yet -> unconfigured
    fsm.fire("provider", "vultr", "resolve")
    assert _leaves(fsm) == ["unconfigured"]

    # the required secret appears at the source -> refresh (env) + re-resolve -> configured
    box["secrets"] = {"api_key": "KEY"}
    fsm.refresh("provider", "vultr")
    fsm.fire("provider", "vultr", "resolve")
    assert _leaves(fsm) == ["unreachable"]  # configured, probe pending

    # the connectivity probe succeeds -> reachable
    fsm.fire("provider", "vultr", "probe_ok")
    assert _leaves(fsm) == ["reachable"]
