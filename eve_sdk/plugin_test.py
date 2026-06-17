"""Conformance harness: validate a single plugin against the published contract.

``run_plugin_test(plugin_path)`` loads a plugin manifest and runs three
categories of checks:

1. **Manifest schema** — loads and validates against
   ``core/schema/plugin-manifest.schema.json`` via :meth:`PluginManifest.validate`
   (covers api_version, kind, id, commands, execs, config_schema).
2. **requires core gate** — validates the ``requires`` shape and enforces
   ``requires.eve`` against :data:`~eve_sdk.plugin_manifest.CORE_VERSION`
   (rejects out-of-range with a readable message).
3. **manageable boundary** (roadmap 204-222) - a provider must be able to
   reach an manageable host on its own (declares access rules + owns bring-up
   commands incl. ``ssh``, ``up``, ``status``); a package must assume an
   already-reachable host (no ``access``, no ``catalog.inits``, no provider
   capabilities, no bring-up commands).

Dry-run dispatch checks (exercising ``up --dry-run``, ``status``, ``ssh
--dry-run`` through the dispatch layer) are deferred to Phase 1 — see the
TODO below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eve_sdk.plugin_manifest import CORE_VERSION, PluginManifest
from eve_sdk.semver import SemverError, satisfies

__all__ = [
    "CheckResult",
    "PluginTestResult",
    "run_plugin_test",
]

# Provider-exclusive commands that represent bring-up / infrastructure
# ownership.  A package declaring any of these violates the manageability
# boundary.  ``down`` and ``status`` appear in both kinds, so they are excluded.
_PROVIDER_EXCLUSIVE_COMMANDS: frozenset[str] = frozenset({
    "resolve", "init", "plan", "up", "start", "stop", "ssh", "ip", "validate",
})

# Capabilities that are meaningful only on provider manifests.
_PROVIDER_CAPABILITIES: frozenset[str] = frozenset({
    "host-ssh", "login", "needs-provider-ip", "password",
})


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single conformance check."""

    name: str
    passed: bool
    message: str


@dataclass
class PluginTestResult:
    """Aggregate result of running ``run_plugin_test`` on one plugin."""

    plugin_path: str
    plugin_id: str | None = None
    kind: str | None = None
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.passed]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_plugin_test(plugin_path: str | os.PathLike[str]) -> PluginTestResult:
    """Validate a single plugin at *plugin_path* against the published contract.

    *plugin_path* may be a directory containing ``eve-plugin.yaml`` or a path
    to the manifest file itself.
    """
    resolved = _resolve_path(plugin_path)
    checks: list[CheckResult] = []

    # -- load ---------------------------------------------------------------
    manifest: dict[str, Any] | None = None
    try:
        manifest = PluginManifest.load(resolved)
    except Exception as error:
        checks.append(CheckResult("manifest-load", False, str(error)))
        return PluginTestResult(str(resolved), checks=checks)

    plugin_id = manifest.get("id")
    kind = manifest.get("kind")
    result = PluginTestResult(str(resolved), plugin_id=plugin_id, kind=kind, checks=checks)

    # -- manifest schema + structural validation ----------------------------
    try:
        PluginManifest.validate(manifest)
        checks.append(CheckResult(
            "manifest-conformance",
            True,
            f"{kind}:{plugin_id} validates against plugin-manifest.schema.json",
        ))
    except ValueError as error:
        checks.append(CheckResult("manifest-conformance", False, str(error)))

    # -- requires.eve core gate (explicit) ----------------------------------
    checks.append(_check_requires_core_gate(manifest))

    # -- manageable boundary ---------------------------------------------
    checks.extend(_check_ssh_readiness(manifest))

    # TODO(phase-1): Add dry-run dispatch checks once the fake-provider
    # substrate exists.  These will exercise ``up --dry-run``, ``status``,
    # and ``ssh --dry-run`` through the dispatch layer to verify the provider
    # actually reaches manageable without real cloud credentials.

    return result


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def _check_requires_core_gate(manifest: dict[str, Any]) -> CheckResult:
    """Explicitly report the ``requires.eve`` core-gate outcome."""
    requires = manifest.get("requires")
    eve_range = requires.get("eve") if isinstance(requires, dict) else None
    if not eve_range:
        return CheckResult(
            "requires-core-gate",
            True,
            "no requires.eve range declared (optional)",
        )
    try:
        ok = satisfies(CORE_VERSION, eve_range)
    except SemverError as error:
        return CheckResult(
            "requires-core-gate",
            False,
            f"requires.eve {eve_range!r} has invalid range: {error}",
        )
    if ok:
        return CheckResult(
            "requires-core-gate",
            True,
            f"requires.eve {eve_range!r} includes core {CORE_VERSION}",
        )
    return CheckResult(
        "requires-core-gate",
        False,
        f"requires.eve {eve_range!r} excludes running core version {CORE_VERSION}",
    )


def _check_ssh_readiness(manifest: dict[str, Any]) -> list[CheckResult]:
    """Assert the manageable boundary (roadmap 204-222)."""
    kind = manifest.get("kind")
    if kind == "provider":
        return _check_provider_boundary(manifest)
    if kind == "package":
        return _check_package_boundary(manifest)
    return [CheckResult(
        "ssh-readiness-boundary",
        False,
        f"cannot evaluate boundary: unknown kind {kind!r}",
    )]


def _check_provider_boundary(manifest: dict[str, Any]) -> list[CheckResult]:
    """A provider must reach manageable on its own — access rules + bring-up commands."""
    checks: list[CheckResult] = []
    commands = manifest.get("commands")
    command_names: set[str] = set(commands.keys()) if isinstance(commands, dict) else set()

    # Must declare access rules (owns SSH identity / bootstrap user).
    access = manifest.get("access")
    if isinstance(access, dict) and len(access) > 0:
        families = sorted(str(k) for k in access)
        checks.append(CheckResult(
            "boundary:provider-access-rules",
            True,
            f"declares access rules for OS families: {', '.join(families)}",
        ))
    else:
        checks.append(CheckResult(
            "boundary:provider-access-rules",
            False,
            "provider must declare access rules (bootstrap/provision/human users) "
            "to reach an manageable host without depending on a package",
        ))

    # Must own the core bring-up commands.
    for required in ("ssh", "up", "status"):
        name = f"boundary:provider-owns-{required}"
        if required in command_names:
            checks.append(CheckResult(
                name, True,
                f"provider owns '{required}' command (owns bring-up)",
            ))
        else:
            checks.append(CheckResult(
                name, False,
                f"provider must own '{required}' command to deliver an manageable host",
            ))

    return checks


def _check_package_boundary(manifest: dict[str, Any]) -> list[CheckResult]:
    """A package must assume an already-reachable host — no bring-up, post-SSH only."""
    checks: list[CheckResult] = []
    commands = manifest.get("commands")
    command_names: set[str] = set(commands.keys()) if isinstance(commands, dict) else set()

    # Must NOT declare access rules — that is provider-owned infrastructure.
    if manifest.get("access"):
        checks.append(CheckResult(
            "boundary:package-no-access",
            False,
            "package must not declare access rules — bring-up/identity is provider-owned",
        ))
    else:
        checks.append(CheckResult(
            "boundary:package-no-access",
            True,
            "package does not declare access rules (assumes manageable host)",
        ))

    # Must NOT contribute catalog.inits — init/bootstrap is pre-SSH, provider-owned.
    catalog = manifest.get("catalog")
    inits = catalog.get("inits") if isinstance(catalog, dict) else None
    if isinstance(inits, list) and len(inits) > 0:
        checks.append(CheckResult(
            "boundary:package-no-init-contribution",
            False,
            f"package must not contribute catalog.inits ({len(inits)} entries) — "
            "init/bootstrap is provider-owned pre-SSH infrastructure",
        ))
    else:
        checks.append(CheckResult(
            "boundary:package-no-init-contribution",
            True,
            "package does not contribute pre-SSH init entries",
        ))

    # Must NOT declare provider-level capabilities.
    capabilities = manifest.get("capabilities")
    caps = set(capabilities) if isinstance(capabilities, list) else set()
    provider_caps = caps & _PROVIDER_CAPABILITIES
    if provider_caps:
        checks.append(CheckResult(
            "boundary:package-no-provider-capabilities",
            False,
            f"package must not declare provider capabilities: {', '.join(sorted(provider_caps))}",
        ))
    else:
        checks.append(CheckResult(
            "boundary:package-no-provider-capabilities",
            True,
            "package does not declare provider-level capabilities",
        ))

    # Must NOT declare bring-up commands.
    bringup = command_names & _PROVIDER_EXCLUSIVE_COMMANDS
    if bringup:
        checks.append(CheckResult(
            "boundary:package-no-bringup-commands",
            False,
            f"package must not declare bring-up commands: {', '.join(sorted(bringup))} "
            "— these are provider-owned",
        ))
    else:
        checks.append(CheckResult(
            "boundary:package-no-bringup-commands",
            True,
            "package does not declare bring-up commands (post-SSH by construction)",
        ))

    return checks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_path(plugin_path: str | os.PathLike[str]) -> Path:
    """Resolve a plugin path that may be a directory or a manifest file."""
    path = Path(plugin_path).resolve()
    if path.is_dir():
        manifest = path / "eve-plugin.yaml"
        if manifest.is_file():
            return manifest
    return path
