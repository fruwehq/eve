"""Migrate persisted eve state files from the pre-FSM vocabulary to the core machine
vocabulary (v4.5 N; ``core/fsm/*.yaml``).

The state graphs moved into Determa State machines with a cleaner state set, so existing
state files must be translated. This is applied on read (idempotent) so upgrades are
transparent; unknown values pass through unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Provider region (core/fsm/instance.yaml). Stable values map identically. The old
# terraform micro-stages (initializing/initialized/planned/changing) are in-flight and
# never stably persisted; if one is found, map it to `unknown` so the next observation
# reconciles reality rather than freezing a mid-operation phase.
PROVIDER_STATE_MIGRATION: dict[str, str] = {
    "unknown": "unknown",
    "running": "running",
    "stopped": "stopped",
    "absent": "absent",
    "error": "error",
    "initializing": "unknown",
    "initialized": "unknown",
    "planned": "unknown",
    "changing": "unknown",
}

# Provisioning region (core/fsm/instance.yaml).
PROVISION_STATE_MIGRATION: dict[str, str] = {
    "unknown": "unprovisioned",
    "provisioning": "provisioning",
    "provisioned": "provisioned",
    "error": "provision_error",
}

# Package machine (core/fsm/package.yaml). `reinstalled` collapses to installed.
PACKAGE_STATE_MIGRATION: dict[str, str] = {
    "unknown": "unknown",
    "installed": "installed",
    "missing": "missing",
    "failed": "failed",
    "removed": "removed",
    "reinstalled": "installed",
    "installing": "installing",
}


def migrate_state_doc(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a persisted state doc with provider/provision/package state
    strings mapped to the core machine vocabulary. Idempotent; unrecognized values and
    all other fields (e.g. ``desired_state``) pass through unchanged."""
    out = dict(doc)
    if "provider_state" in out:
        out["provider_state"] = PROVIDER_STATE_MIGRATION.get(out["provider_state"], out["provider_state"])
    if "provision_state" in out:
        out["provision_state"] = PROVISION_STATE_MIGRATION.get(out["provision_state"], out["provision_state"])
    packages = out.get("package_state")
    if isinstance(packages, Mapping):
        migrated: dict[str, Any] = {}
        for pkg_id, entry in packages.items():
            if isinstance(entry, Mapping) and "status" in entry:
                status = entry["status"]
                migrated[pkg_id] = dict(entry) | {"status": PACKAGE_STATE_MIGRATION.get(status, status)}
            else:
                migrated[pkg_id] = entry
        out["package_state"] = migrated
    return out
