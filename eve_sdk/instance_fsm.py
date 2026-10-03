"""Instance-lifecycle transitions, driven by the core instance machine.

The single authority for how an instance operation moves its ``provider_state``,
``provision_state``, or per-package state: dispatch computes the next state by
**firing an event into the corresponding core machine** seeded from the persisted
state, not from a second, hand-maintained transition table. The machine bundle *is*
the lifecycle; this module is the thin, fast adapter Eve calls (and the persisted
state a status read sees is therefore exactly what the machine produced — bug N).

The engine is pure-functional (``create``/``dispatch`` over plain aggregate-state
dicts), so "seeding from the persisted state" is: reach each lifecycle leaf once
from a fresh aggregate by replaying a short event prefix, cache that aggregate per
leaf, then dispatch the real event against it — dispatch never mutates its input, so
the cache stays valid. This is deliberately limited to these context-free finite
graphs; a future stateful machine must persist and restore its full aggregate instead
of extending seed-by-replay.
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
_PROVIDER_SEED_EVENTS: dict[str, list[str]] = {
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

PROVISION_LEAVES = {"unknown", "provisioning", "provisioned", "error"}

_PROVISION_SEED_EVENTS: dict[str, list[str]] = {
    "unknown": [],
    "provisioning": ["provision"],
    "provisioned": ["provision", "provision_ok"],
    "error": ["provision", "provision_fail"],
}

PACKAGE_LEAVES = {
    "failed",
    "installed",
    "installing",
    "missing",
    "removed",
    "removing",
    "unknown",
}

_PACKAGE_SEED_EVENTS: dict[str, list[str]] = {
    "failed": ["observe_failed"],
    "installed": ["found"],
    "installing": ["install"],
    "missing": ["absent"],
    "removed": ["remove", "remove_ok"],
    "removing": ["remove"],
    "unknown": [],
}

_bundles: dict[str, Any] = {}
_seeded: dict[tuple[str, str, str], dict[str, Any]] = {}
_sequence = 0


def _bundle(filename: str) -> Any:
    bundle = _bundles.get(filename)
    if bundle is None:
        bundle_yaml = (Workdir.repo_root() / "core" / "fsm" / filename).read_text(
            encoding="utf-8"
        )
        bundle = engine.load_bundle(bundle_yaml)
        _bundles[filename] = bundle
    return bundle


def _dispatch(bundle: Any, state: dict[str, Any], event: str) -> dict[str, Any]:
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
    result = engine.dispatch(bundle, state, {"input": envelope})
    new_state: dict[str, Any] = result["state"]
    return new_state


def _seeded_aggregate(
    filename: str, machine_id: str, leaf: str, seed_events: dict[str, list[str]]
) -> dict[str, Any]:
    """The cached aggregate whose selected lifecycle machine sits at ``leaf``."""
    bundle = _bundle(filename)
    cache_key = (filename, machine_id, leaf)
    state = _seeded.get(cache_key)
    if state is None:
        state = engine.create(
            bundle, machine_id, leaf, f"eve-seed-{machine_id}-{leaf}", None
        )["state"]
        for event in seed_events[leaf]:
            state = _dispatch(bundle, state, event)
        assert leaf_names(state) == [leaf]
        _seeded[cache_key] = state
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
    bundle = _bundle("instance.yaml")
    moved = leaf_names(
        _dispatch(
            bundle,
            _seeded_aggregate(
                "instance.yaml", "instance_provider", leaf, _PROVIDER_SEED_EVENTS
            ),
            event,
        )
    )
    return moved[0] if moved else leaf


def provision_event(op_status: str) -> str | None:
    """Map a provision operation status to an instance-provision event."""
    return {
        "running": "provision",
        "succeeded": "provision_ok",
        "failed": "provision_fail",
    }.get(op_status)


def provision_state_after(current: str, event: str | None) -> str | None:
    """The provision_state after firing ``event`` from ``current``."""
    if event is None:
        return None
    leaf = current if current in PROVISION_LEAVES else "unknown"
    bundle = _bundle("instance.yaml")
    moved = leaf_names(
        _dispatch(
            bundle,
            _seeded_aggregate(
                "instance.yaml", "instance_provision", leaf, _PROVISION_SEED_EVENTS
            ),
            event,
        )
    )
    return moved[0] if moved else leaf


def package_operation_event(command: str, op_status: str) -> str | None:
    """Map a package operation status to a package-machine event."""
    if command in {"install", "reinstall"}:
        return {
            "failed": "install_fail",
            "running": "install",
            "succeeded": "install_ok",
        }.get(op_status)
    if command == "down":
        return {
            "failed": "remove_fail",
            "running": "remove",
            "succeeded": "remove_ok",
        }.get(op_status)
    return None


def package_observation_event(status: str) -> str | None:
    """Map a validated package status result to an observation event."""
    return {
        "failed": "observe_failed",
        "installed": "found",
        "missing": "absent",
        "unknown": "observe_unknown",
    }.get(status)


def package_state_after(current: str, event: str | None) -> str | None:
    """The package state after firing ``event`` from ``current``."""
    if event is None:
        return None
    leaf = current if current in PACKAGE_LEAVES else "unknown"
    bundle = _bundle("package.yaml")
    moved = leaf_names(
        _dispatch(
            bundle,
            _seeded_aggregate("package.yaml", "package", leaf, _PACKAGE_SEED_EVENTS),
            event,
        )
    )
    return moved[0] if moved else leaf
