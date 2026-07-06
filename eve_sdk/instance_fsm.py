"""Instance-lifecycle transitions, driven by the core instance machine.

The single authority for how a provider operation moves an instance's
``provider_state``: dispatch computes the next state by **firing an event into
``core/fsm/instance.yaml``** seeded from the persisted state, not from a second,
hand-maintained transition table. The machine YAML *is* the lifecycle; this
module is the thin, fast adapter eve calls (and the persisted ``provider_state``
a status read sees is therefore exactly what the machine produced — bug N).

Only the provider region is driven here; the provision region is seeded with a
constant placeholder so a provider event never depends on provision naming (the
persisted ``provision_state`` field keeps its own vocabulary until that region is
wired the same way).
"""

from __future__ import annotations

from typing import Any

from eve_sdk import fsm as _fsm
from eve_sdk.workdir import Workdir

# The statechart engine, reached through the one module that owns the coupling.
engine = _fsm.engine

# Leaf sets, so we can pick the provider-region leaf out of ``active_leaf_names``
# (whose order across orthogonal regions is not guaranteed). These mirror the
# regions declared in core/fsm/instance.yaml.
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
# The provision leaf we seed while firing provider events; any valid provision
# leaf works because provider events do not touch the provision region.
_SEED_PROVISION = "unprovisioned"

_host: Any = None
_instance: Any = None


def _machine() -> tuple[Any, Any]:
    """Lazily build a reusable host + root instance for the core instance machine."""
    global _host, _instance
    if _instance is None:
        machine_yaml = (Workdir.repo_root() / "core" / "fsm" / "instance.yaml").read_text(encoding="utf-8")
        host = engine.Host()
        host.register_all(engine.load_definitions(machine_yaml))
        instance = host.create_root(host.machines["instance"], "instance", external={"desired": "unknown"})
        host.run_to_quiescence()
        _host, _instance = host, instance
    return _host, _instance


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
    rejects the event from ``current`` (an operation that doesn't apply in that
    state), the state is unchanged and ``current`` is returned.
    """
    if event is None:
        return None
    provider = current if current in PROVIDER_LEAVES else "unknown"
    host, instance = _machine()
    instance.load_snapshot(
        {
            "def_id": "instance",
            "def_version": 1,
            "id": "instance",
            "parent_id": None,
            "status": "active",
            "state_config": ["top", f"top.{provider}", f"top.{_SEED_PROVISION}"],
            "esvs": {"top": {"desired": "unknown"}},
            "queue": [],
            "deferred": [],
            "timers": [],
            "dead_letter": [],
            "history": {},
        }
    )
    host.deliver("instance", event, {})
    host.run_to_quiescence()
    for leaf in instance.active_leaf_names():
        if leaf in PROVIDER_LEAVES:
            return str(leaf)
    return provider
