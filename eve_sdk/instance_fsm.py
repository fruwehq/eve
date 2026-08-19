"""Instance-lifecycle transitions, driven by the core instance machine.

The single authority for how a provider operation moves an instance's
``provider_state``: dispatch computes the next state by **firing an event into the
``instance_provider`` machine of ``core/fsm/instance.yaml``** seeded from the
persisted state, not from a second, hand-maintained transition table. The machine
bundle *is* the lifecycle; this module is the thin, fast adapter eve calls (and the
persisted ``provider_state`` a status read sees is therefore exactly what the
machine produced — bug N).

The engine is pure-functional (``create``/``dispatch`` over plain aggregate-state
dicts), so "seeding from the persisted state" is: reach each provider leaf once from
a fresh aggregate by replaying a short event prefix, cache that aggregate per leaf,
then dispatch the real event against it — dispatch never mutates its input, so the
cache stays valid. Only the provider machine is driven here; the persisted
``provision_state`` field keeps its own vocabulary until the ``instance_provision``
machine is wired the same way.
"""

from __future__ import annotations

from typing import Any

from eve_sdk.fsm import engine, leaf_names
from eve_sdk.workdir import Workdir

# The provider-machine leaves (mirrors core/fsm/instance.yaml, machine
# instance_provider). Persisted provider_state values outside this set (legacy or
# corrupt) seed as `unknown`.
PROVIDER_LEAVES = {
    "unknown",
    "creating",
    "starting",
    "stopping",
    "destroying",
    "running",
    "stopped",
    "absent",
    "error",
}

# The shortest event prefix that reaches each leaf from a fresh aggregate; every
# concrete state accepts every operator command, so each transient is one event away
# and `error` is two.
_SEED_EVENTS: dict[str, list[str]] = {
    "unknown": [],
    "creating": ["create"],
    "starting": ["start"],
    "stopping": ["stop"],
    "destroying": ["destroy"],
    "running": ["observe_running"],
    "stopped": ["observe_stopped"],
    "absent": ["observe_absent"],
    "error": ["create", "op_fail"],
}

_MACHINE_ID = "instance_provider"

_bundle: Any = None
_seeded: dict[str, dict[str, Any]] = {}
_sequence = 0


def _dispatch(state: dict[str, Any], event: str) -> dict[str, Any]:
    """One input-event RTC step; returns the (new) aggregate state."""
    global _sequence
    _sequence += 1
    envelope = {
        "event": event,
        "event_id": f"eve-instance-{_sequence}",
        "target": {
            "root": {
                "root_instance_id": state["root_instance_id"],
                "root_runtime_id": state["root_runtime_id"],
            }
        },
        "payload": {},
    }
    result = engine.dispatch(_bundle, state, {"input": envelope})
    new_state: dict[str, Any] = result["state"]
    return new_state


def _seeded_aggregate(leaf: str) -> dict[str, Any]:
    """The cached aggregate whose provider machine sits at ``leaf``."""
    global _bundle
    if _bundle is None:
        bundle_yaml = (Workdir.repo_root() / "core" / "fsm" / "instance.yaml").read_text(encoding="utf-8")
        _bundle = engine.load_bundle(bundle_yaml)
    state = _seeded.get(leaf)
    if state is None:
        state = engine.create(_bundle, _MACHINE_ID, leaf, f"eve-seed-{leaf}", None)["state"]
        for event in _SEED_EVENTS[leaf]:
            state = _dispatch(state, event)
        assert leaf_names(state) == [leaf]
        _seeded[leaf] = state
    return state


def dispatch_event(command: str | None, op_status: str) -> str | None:
    """Map a dispatched ``(command, op_status)`` to an instance-machine event.

    ``None`` means "leave ``provider_state`` unchanged" (read-only commands, and
    the terraform sub-stages while an operation is still in flight).
    """
    command = command or ""
    if op_status == "running":
        # Operation in flight -> the machine's transient state.
        return {"up": "create", "start": "start", "stop": "stop", "down": "destroy"}.get(command)
    if op_status == "failed":
        return None if command in {"resolve", "status", "ip", "ssh"} else "op_fail"
    if op_status != "succeeded":
        return None
    # Success -> the terminal event for the operation. init/plan are terraform
    # sub-stages of an up: they signal creation underway (`create` is a no-op once
    # already creating, so it only advances from unknown/absent/error).
    return {
        "up": "created_ok",
        "start": "started_ok",
        "stop": "stopped_ok",
        "down": "destroyed_ok",
        "init": "create",
        "plan": "create",
    }.get(command)


def provider_state_after(current: str, event: str | None) -> str | None:
    """The provider_state after firing ``event`` from ``current``.

    Returns ``None`` when there is no event (no change to persist). If the machine
    leaves the event unhandled from ``current`` (an outcome event that doesn't apply
    in that state), the state is unchanged and ``current`` is returned.
    """
    if event is None:
        return None
    leaf = current if current in PROVIDER_LEAVES else "unknown"
    moved = leaf_names(_dispatch(_seeded_aggregate(leaf), event))
    return moved[0] if moved else leaf
