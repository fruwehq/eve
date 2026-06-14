"""Poetry-style single-version, fail-on-conflict plugin dependency resolver.

Given the plugin candidates available from the synced sources (each a semver
version derived from its pinned git tag) and their ``requires`` blocks, resolve
**exactly one version per plugin id**:

- **Core gate** — a candidate whose ``requires.eve`` excludes the running core
  version is rejected with a clear message (no silent "works mostly").
- **Single version** — collect every range constraint on an id from all
  dependents' ``requires.plugins`` and pick the highest available version that
  satisfies them all.
- **Conflicts are hard errors** — if no single version of an id satisfies all
  its ranges, resolution fails with a readable report naming each requirer and
  its range (exactly like pip/poetry). eve never loads two versions of one id.

The resolver is pure: it operates on ``PluginCandidate`` records so it is fully
unit-testable without git or disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eve_sdk.semver import SemverError, parse_version, satisfies


class ResolutionError(Exception):
    """Base class for unresolvable dependency situations."""


class CoreIncompatibleError(ResolutionError):
    """A required plugin declares a ``requires.eve`` excluding the core version."""


class DependencyConflictError(ResolutionError):
    """No single version of a plugin id satisfies all its range constraints."""


@dataclass(frozen=True)
class PluginCandidate:
    """One available version of a plugin id, with its declared requirements."""

    id: str
    version: str
    requires_eve: str | None = None
    requires_plugins: dict[str, str] = field(default_factory=dict)
    source_id: str | None = None


@dataclass(frozen=True)
class Resolved:
    id: str
    version: str
    source_id: str | None
    required_by: tuple[str, ...]


def resolve(candidates: list[PluginCandidate], core_version: str) -> list[Resolved]:
    """Resolve one version per plugin id. Raises on core-gate / conflict failures.

    All supplied candidates are treated as roots (the user added their sources);
    their ``requires.plugins`` then constrain which versions are chosen.
    """
    by_id: dict[str, list[PluginCandidate]] = {}
    for candidate in candidates:
        by_id.setdefault(candidate.id, []).append(candidate)

    # 1. Core gate — reject any candidate whose requires.eve excludes core.
    for candidate in candidates:
        if candidate.requires_eve is None:
            continue
        try:
            ok = satisfies(core_version, candidate.requires_eve)
        except SemverError as error:
            raise CoreIncompatibleError(
                f"{candidate.id} {candidate.version}: invalid requires.eve "
                f"{candidate.requires_eve!r}: {error}"
            ) from error
        if not ok:
            raise CoreIncompatibleError(
                f"{candidate.id} {candidate.version} requires eve {candidate.requires_eve!r}, "
                f"but the running core is {core_version}"
            )

    # 2. Gather every range constraint on each id from all dependents.
    constraints: dict[str, list[tuple[str, str]]] = {}  # id -> [(requirer, range)]
    for candidate in candidates:
        for dep_id, dep_range in candidate.requires_plugins.items():
            constraints.setdefault(dep_id, []).append(
                (f"{candidate.id} {candidate.version}", dep_range)
            )

    # 3. A required dependency that no source provides is a hard error.
    for dep_id, reqs in constraints.items():
        if dep_id not in by_id:
            requirers = ", ".join(f"{who} (needs {rng})" for who, rng in reqs)
            raise DependencyConflictError(
                f"unsatisfied dependency: no source provides plugin {dep_id!r} required by {requirers}"
            )

    # 4. Choose one version per id: highest that satisfies every constraint.
    resolved: list[Resolved] = []
    for plugin_id, versions in sorted(by_id.items()):
        reqs = constraints.get(plugin_id, [])
        satisfying = [c for c in versions if _satisfies_all(c.version, reqs)]
        if not satisfying:
            raise DependencyConflictError(_conflict_report(plugin_id, versions, reqs))
        chosen = max(satisfying, key=lambda c: parse_version(c.version))
        resolved.append(
            Resolved(
                id=chosen.id,
                version=chosen.version,
                source_id=chosen.source_id,
                required_by=tuple(who for who, _ in reqs),
            )
        )
    return resolved


def candidate_from_manifest(manifest: dict, version: str, source_id: str | None = None) -> PluginCandidate:
    """Build a candidate from a plugin manifest dict + its version (from the source tag)."""
    requires = manifest.get("requires") if isinstance(manifest.get("requires"), dict) else {}
    plugins = requires.get("plugins") if isinstance(requires.get("plugins"), dict) else {}
    return PluginCandidate(
        id=str(manifest["id"]),
        version=version,
        requires_eve=requires.get("eve") if isinstance(requires.get("eve"), str) else None,
        requires_plugins={str(k): str(v) for k, v in plugins.items()},
        source_id=source_id,
    )


def _satisfies_all(version: str, reqs: list[tuple[str, str]]) -> bool:
    return all(satisfies(version, rng) for _, rng in reqs)


def _conflict_report(plugin_id: str, versions: list[PluginCandidate], reqs: list[tuple[str, str]]) -> str:
    available = ", ".join(sorted(c.version for c in versions)) or "(none)"
    lines = [
        f"dependency conflict on plugin {plugin_id!r}: no single version satisfies all requirements.",
        f"  available versions: {available}",
        "  required by:",
    ]
    for who, rng in reqs:
        lines.append(f"    - {who} needs {plugin_id} {rng}")
    lines.append("  resolve by bumping/pinning a source so the ranges overlap (like a pip/poetry conflict).")
    return "\n".join(lines)
