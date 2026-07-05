"""eve FSM platform — the single seam between eve and the Determa State statechart engine.

Machines are declared in **Determa State YAML** by the plugin that owns them (a provider, a
package, ...). eve resolves each machine's ``external`` esvs (settings + secrets)
through **one shared resolver** and seeds them as the machine's context, so status,
dispatch, and connectivity can never see different config (v4.5 bugs N/O). The engine
is the swappable unit; this module is the only place eve touches it.

Side effects are host-driven: engine actions are sandboxed, so eve runs the real
command (probe, terraform, provision) and delivers the outcome back as an event
(e.g. ``probe_ok`` / ``probe_fail``). The machine only ever holds state + context.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

# The statechart engine (Determa State; formerly harel). Import it behind one name so
# eve's only coupling to it is this module.
try:  # pragma: no cover - the branch taken depends only on which package is installed
    import determa.state as engine
except ModuleNotFoundError:  # pre-rename package name
    import harel as engine

# Resolve a machine's declared ``external`` esvs from eve settings/secrets:
#   (scope, key, external_names) -> {name: value}
# Injected so resolution lives in exactly one place (the bug-M/O helper) and the
# platform stays testable without real config on disk.
ContextResolver = Callable[[str, str, list[str]], dict[str, Any]]


class EveFsm:
    """Loads plugin-declared Determa State machines and tracks their live instances."""

    def __init__(self, resolve_context: ContextResolver) -> None:
        self._resolve = resolve_context
        self._host = engine.Host()
        self._raw: dict[str, dict[str, Any]] = {}
        self._machine: dict[str, Any] = {}

    def load(self, scope: str, machine_yaml: str) -> None:
        """Register the machine a plugin ships for ``scope`` (its first document)."""
        defs = engine.load_definitions(machine_yaml)
        for definition in defs:
            engine.validate(definition.raw)
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


def provider_context_resolver() -> ContextResolver:
    """The real :data:`ContextResolver` for provider machines.

    Each declared external esv is named as its eve env var (e.g. ``VULTR_API_KEY``) and
    resolved from the *one* path dispatch uses — ``os.environ`` +
    ``ConfigEnv.environment()`` + injected secrets — so a provider's FSM context and what
    dispatch runs with are identical (v4.5 bug M: status ≡ dispatch). ``key`` is the
    provider id.

    (Systemic follow-up: drop ambient ``os.environ`` from *both* this resolver and
    dispatch so no config reaches a plugin behind eve's back; kept here for now to
    preserve exact parity.)
    """
    from eve_sdk.config import ConfigEnv
    from eve_sdk.provider_command import _inject_secrets, _load_public_plugin

    def resolve(scope: str, key: str, names: list[str]) -> dict[str, Any]:
        env = dict(os.environ)
        env.update(ConfigEnv.environment())
        plugin = _load_public_plugin("provider", key)
        env = _inject_secrets(key, plugin, env)
        return {name: env.get(name, "") for name in names}

    return resolve


def provider_configured_resolver() -> ContextResolver:
    """The :data:`ContextResolver` for the core provider machine (``core/fsm/provider.yaml``).

    Derives ``is_configured`` = True iff every ``required`` config_schema secret/setting
    of the provider resolves to a non-empty value via the one shared path (``os.environ``
    + ``ConfigEnv.environment()`` + injected secrets). So "configured" is eve-resolved,
    never a plugin's ambient self-report (the AWS-off-``~/.aws`` bug is structurally
    impossible). ``key`` is the provider id; ``names`` is typically ``["is_configured"]``.
    """
    from eve_sdk.config import ConfigEnv
    from eve_sdk.provider_command import _inject_secrets, _load_public_plugin

    def resolve(scope: str, key: str, names: list[str]) -> dict[str, Any]:
        plugin = _load_public_plugin("provider", key)
        env = dict(os.environ)
        env.update(ConfigEnv.environment())
        env = _inject_secrets(key, plugin, env)
        schema = plugin.get("config_schema") or {}
        required = [
            (field, spec)
            for section in ("secrets", "settings")
            for field, spec in (schema.get(section) or {}).items()
            if isinstance(spec, Mapping) and spec.get("required")
        ]

        def present(field: str, spec: Mapping[str, Any]) -> bool:
            candidates = [field]
            env_var = spec.get("env_var")
            if env_var:
                candidates.append(str(env_var))
            return any(env.get(candidate) for candidate in candidates)

        values: dict[str, Any] = {"is_configured": all(present(f, s) for f, s in required)}
        return {name: values.get(name, "") for name in names}

    return resolve
