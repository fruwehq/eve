"""eve FSM platform — the single seam between eve and the Determa State statechart engine.

Machines are declared as **Determa State format-1 bundles** by the plugin that owns
them (a provider, a package, ...). eve resolves each machine's ``external`` variables
(settings + secrets) through **one shared resolver** and seeds them as creation
bindings, so status, dispatch, and connectivity can never see different config (v4.5
bugs N/O). The engine is the swappable unit; this module is the only place eve
touches it.

The engine's interface is pure-functional (spec §8): ``create``/``dispatch`` map a
plain aggregate-state dict to the next one — no engine-held mutable objects. This
platform keeps each live aggregate state in memory per ``(scope, key)``.

Side effects are host-driven: eve runs the real command (probe, terraform,
provision) and delivers the outcome back as an event (e.g. ``probe_ok`` /
``probe_fail``). The machine only ever holds state + context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

# The statechart engine (Determa State). Import it behind one name so eve's only
# coupling to it is this module; re-bound as a defined name so it is an explicit
# export (other eve modules read it as ``eve_sdk.fsm.engine``).
import determa.state as _engine_mod

engine = _engine_mod


class FsmError(Exception):
    pass


# Resolve a machine's declared ``external`` variables from eve settings/secrets:
#   (scope, key, external_names) -> {name: value}
# Injected so resolution lives in exactly one place (the bug-M/O helper) and the
# platform stays testable without real config on disk.
ContextResolver = Callable[[str, str, list[str]], dict[str, Any]]


def _machine_doc(bundle: Any, machine_id: str) -> dict[str, Any]:
    for machine in bundle.raw["machines"]:
        if machine["machine_id"] == machine_id:
            return dict(machine)
    raise FsmError(f"machine not found in bundle: {machine_id}")


def external_names(bundle: Any, machine_id: str) -> list[str]:
    """The machine's declared root ``external`` variable names (eve-resolved)."""
    variables = _machine_doc(bundle, machine_id).get("root", {}).get("variables", {}) or {}
    return [name for name, spec in variables.items() if isinstance(spec, Mapping) and spec.get("external")]


def leaf_names(aggregate: Mapping[str, Any]) -> list[str]:
    """The root runtime's active leaf-state names (last path segment, sorted)."""
    runtime = aggregate["runtimes"][aggregate["root_runtime_id"]]
    active = list(runtime["active"])
    leaves = [
        path
        for path in active
        if path != "root" and not any(other.startswith(path + ".") for other in active)
    ]
    return sorted(path.split(".")[-1] for path in leaves)


class EveFsm:
    """Loads plugin-declared Determa State bundles and tracks their live aggregates."""

    def __init__(self, resolve_context: ContextResolver) -> None:
        self._resolve = resolve_context
        self._bundle: dict[str, Any] = {}
        self._machine_id: dict[str, str] = {}
        self._aggregate: dict[str, dict[str, Any]] = {}
        self._sequence = 0

    def load(self, scope: str, bundle_yaml: str, machine_id: str | None = None) -> None:
        """Register the bundle a plugin ships for ``scope``.

        ``machine_id`` selects the machine driven under this scope; defaults to the
        bundle's first machine.
        """
        bundle = engine.load_bundle(bundle_yaml)
        self._bundle[scope] = bundle
        self._machine_id[scope] = machine_id or str(bundle.raw["machines"][0]["machine_id"])

    def _key(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def _event_id(self) -> str:
        self._sequence += 1
        return f"eve-{self._sequence}"

    def aggregate(self, scope: str, key: str) -> dict[str, Any]:
        """The live aggregate state for ``(scope, key)``; created and seeded on first use."""
        composite = self._key(scope, key)
        state = self._aggregate.get(composite)
        if state is None:
            bundle = self._bundle[scope]
            machine_id = self._machine_id[scope]
            external = self._resolve(scope, key, external_names(bundle, machine_id))
            bindings = {"external": external} if external else None
            result = engine.create(bundle, machine_id, composite, self._event_id(), bindings)
            if result["status"] == "rejected" or result["state"] is None:
                raise FsmError(f"cannot create {composite}: {result['rejection']}")
            state = result["state"]
            self._aggregate[composite] = state
        return state

    def fire(self, scope: str, key: str, event: str, payload: Mapping[str, Any] | None = None) -> bool:
        """Deliver an input event through one RTC step. Returns True iff it was handled."""
        state = self.aggregate(scope, key)
        envelope = {
            "event": event,
            "event_id": self._event_id(),
            "target": {
                "root": {
                    "root_instance_id": state["root_instance_id"],
                    "root_runtime_id": state["root_runtime_id"],
                }
            },
            "payload": dict(payload or {}),
        }
        result = engine.dispatch(self._bundle[scope], state, {"input": envelope})
        if result["disposition"] in {"handled", "unhandled"}:
            self._aggregate[self._key(scope, key)] = result["state"]
        return bool(result["disposition"] == "handled")

    def refresh(self, scope: str, key: str) -> dict[str, Any]:
        """Re-resolve settings/secrets; deliver an ``env`` event with what changed.

        The machine's ``env`` handler adopts the new values via ``refresh``. Returns
        the changed subset (empty if nothing moved).
        """
        current = self.context(scope, key)
        latest = self._resolve(scope, key, external_names(self._bundle[scope], self._machine_id[scope]))
        changed = {name: value for name, value in latest.items() if current.get(name) != value}
        if changed:
            self.fire(scope, key, "env", {"changed": changed})
        return changed

    def leaves(self, scope: str, key: str) -> list[str]:
        """The active leaf-state names (sorted)."""
        return leaf_names(self.aggregate(scope, key))

    def state(self, scope: str, key: str) -> str:
        """The active leaf state (first, for single-region machines)."""
        leaves = self.leaves(scope, key)
        return leaves[0] if leaves else ""

    def context(self, scope: str, key: str) -> dict[str, Any]:
        """The machine's root-scope variables — the one place commands read config."""
        aggregate = self.aggregate(scope, key)
        runtime = aggregate["runtimes"][aggregate["root_runtime_id"]]
        return dict(runtime["scopes"].get("root", {}))

    def view(self, scope: str, key: str) -> dict[str, Any]:
        """State + context + status, for status/TUI/CLI rendering."""
        aggregate = self.aggregate(scope, key)
        return {
            "state": self.leaves(scope, key),
            "context": self.context(scope, key),
            "status": str(aggregate["status"]),
        }


def provider_context_resolver() -> ContextResolver:
    """The real :data:`ContextResolver` for provider machines.

    Each declared external variable is named as its eve env var (e.g. ``VULTR_API_KEY``)
    and resolved from the one environment builder dispatch uses, so a provider's
    FSM context and what dispatch runs with are identical (v4.5 bug M: status ≡
    dispatch). ``key`` is the provider id.

    (Systemic follow-up: drop ambient ``os.environ`` from *both* this resolver and
    dispatch so no config reaches a plugin behind eve's back; kept here for now to
    preserve exact parity.)
    """
    from eve_sdk.provider_command import _load_public_plugin, resolved_provider_environment

    def resolve(scope: str, key: str, names: list[str]) -> dict[str, Any]:
        plugin = _load_public_plugin("provider", key)
        env = resolved_provider_environment(key, plugin)
        return {name: env.get(name, "") for name in names}

    return resolve


def provider_configured_resolver() -> ContextResolver:
    """The :data:`ContextResolver` for the core provider machine (``core/fsm/provider.yaml``).

    Derives ``is_configured`` from both universally ``required`` fields and the
    optional ``required_any`` alternatives. Every universal field must be set,
    and at least one alternative group must be complete. So "configured" is
    eve-resolved, never a plugin's connectivity self-report. ``key`` is the
    provider id; ``names`` is typically ``["is_configured"]``.
    """
    from eve_sdk.provider_command import _load_public_plugin, resolved_provider_environment

    def resolve(scope: str, key: str, names: list[str]) -> dict[str, Any]:
        plugin = _load_public_plugin("provider", key)
        env = resolved_provider_environment(key, plugin)
        schema = plugin.get("config_schema") or {}
        required = [
            (field, spec)
            for section in ("config", "secrets")
            for field, spec in (schema.get(section) or {}).items()
            if isinstance(spec, Mapping) and spec.get("required")
        ]

        def present(field: str, spec: Mapping[str, Any]) -> bool:
            candidates = [field]
            env_var = spec.get("env_var")
            if isinstance(env_var, list):
                candidates.extend(str(name) for name in env_var)
            elif env_var:
                candidates.append(str(env_var))
            return any(env.get(candidate) for candidate in candidates)

        alternatives = schema.get("required_any") or []

        def referenced_present(reference: str) -> bool:
            section, field = reference.split(".", 1)
            spec = (schema.get(section) or {}).get(field)
            return isinstance(spec, Mapping) and present(field, spec)

        required_ok = all(present(field, spec) for field, spec in required)
        alternatives_ok = not alternatives or any(
            all(referenced_present(str(reference)) for reference in group)
            for group in alternatives
        )
        values: dict[str, Any] = {
            "is_configured": required_ok and alternatives_ok
        }
        return {name: values.get(name, "") for name in names}

    return resolve
