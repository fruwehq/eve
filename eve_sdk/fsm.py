"""eve FSM platform — the single seam between eve and the harel statechart engine.

Machines are declared in **harel YAML** by the plugin that owns them (a provider, a
package, ...). eve resolves each machine's ``external`` esvs (settings + secrets)
through **one shared resolver** and seeds them as the machine's context, so status,
dispatch, and connectivity can never see different config (v4.5 bugs N/O). The harel
engine is the swappable unit; this module is the only place eve touches it.

Side effects are host-driven: harel actions are sandboxed, so eve runs the real
command (probe, terraform, provision) and delivers the outcome back as an event
(e.g. ``probe_ok`` / ``probe_fail``). The machine only ever holds state + context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import harel

# Resolve a machine's declared ``external`` esvs from eve settings/secrets:
#   (scope, key, external_names) -> {name: value}
# Injected so resolution lives in exactly one place (the bug-M/O helper) and the
# platform stays testable without real config on disk.
ContextResolver = Callable[[str, str, list[str]], dict[str, Any]]


class EveFsm:
    """Loads plugin-declared harel machines and tracks their live instances."""

    def __init__(self, resolve_context: ContextResolver) -> None:
        self._resolve = resolve_context
        self._host = harel.Host()
        self._raw: dict[str, dict[str, Any]] = {}
        self._machine: dict[str, Any] = {}

    def load(self, scope: str, machine_yaml: str) -> None:
        """Register the harel machine a plugin ships for ``scope`` (its first document)."""
        defs = harel.load_definitions(machine_yaml)
        for definition in defs:
            harel.validate(definition.raw)
        self._host.register_all(defs)
        root = defs[0]
        self._raw[scope] = root.raw
        self._machine[scope] = self._host.machines[root.raw["id"]]

    @staticmethod
    def _external_names(raw: Mapping[str, Any]) -> list[str]:
        esvs = raw.get("top", {}).get("esvs", {}) or {}
        return [name for name, spec in esvs.items() if isinstance(spec, Mapping) and spec.get("external")]

    def _iid(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def instance(self, scope: str, key: str) -> Any:
        """The live instance for ``(scope, key)``; created and seeded on first use."""
        iid = self._iid(scope, key)
        inst = self._host.instances.get(iid)
        if inst is None:
            external = self._resolve(scope, key, self._external_names(self._raw[scope]))
            inst = self._host.create_root(self._machine[scope], iid, external=external)
            self._host.run_to_quiescence()
        return inst

    def fire(self, scope: str, key: str, event: str, payload: Mapping[str, Any] | None = None) -> bool:
        """Deliver an event and run to quiescence. Returns False if it was rejected."""
        self.instance(scope, key)
        accepted = self._host.deliver(self._iid(scope, key), event, dict(payload or {}))
        self._host.run_to_quiescence()
        return accepted

    def refresh(self, scope: str, key: str) -> dict[str, Any]:
        """Re-resolve settings/secrets; deliver an ``env`` event with what changed.

        The machine's ``env`` handler adopts the new values via ``refresh``. Returns
        the changed subset (empty if nothing moved).
        """
        inst = self.instance(scope, key)
        current = dict(inst.resolved_esvs())
        latest = self._resolve(scope, key, self._external_names(self._raw[scope]))
        changed = {name: value for name, value in latest.items() if current.get(name) != value}
        if changed:
            self._host.deliver(self._iid(scope, key), "env", {"changed": changed})
            self._host.run_to_quiescence()
        return changed

    def state(self, scope: str, key: str) -> str:
        """The active leaf state (first, for non-orthogonal machines)."""
        leaves = self.instance(scope, key).active_leaf_names()
        return leaves[0] if leaves else ""

    def context(self, scope: str, key: str) -> dict[str, Any]:
        """The machine's resolved context (esvs) — the one place commands read config."""
        return dict(self.instance(scope, key).resolved_esvs())

    def view(self, scope: str, key: str) -> dict[str, Any]:
        """State + context + status, for status/TUI/CLI rendering."""
        inst = self.instance(scope, key)
        return {
            "state": list(inst.active_leaf_names()),
            "context": dict(inst.resolved_esvs()),
            "status": inst.status.name.lower(),
        }
