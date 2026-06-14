"""Poetry-style resolver: core gate, single-version selection, conflict reports."""

from __future__ import annotations

import pytest

from eve_sdk.resolver import (
    CoreIncompatibleError,
    DependencyConflictError,
    PluginCandidate,
    candidate_from_manifest,
    resolve,
)

CORE = "4.0"


def c(id_: str, version: str, *, eve: str | None = None, plugins: dict | None = None) -> PluginCandidate:
    return PluginCandidate(id=id_, version=version, requires_eve=eve, requires_plugins=plugins or {}, source_id=id_)


def test_resolves_simple_graph() -> None:
    cands = [
        c("ubuntu", "1.3.0"),
        c("desktop", "1.0.0", eve=">=4.0,<5.0", plugins={"ubuntu": ">=1.2,<2.0"}),
    ]
    resolved = {r.id: r.version for r in resolve(cands, CORE)}
    assert resolved == {"ubuntu": "1.3.0", "desktop": "1.0.0"}


def test_picks_highest_satisfying_version() -> None:
    cands = [c("foo", "1.2.0"), c("foo", "1.5.0"), c("bar", "1.0.0", plugins={"foo": "^1.0"})]
    resolved = {r.id: r.version for r in resolve(cands, CORE)}
    assert resolved["foo"] == "1.5.0"


def test_records_required_by() -> None:
    cands = [c("foo", "1.0.0"), c("bar", "2.0.0", plugins={"foo": "^1"})]
    resolved = {r.id: r for r in resolve(cands, CORE)}
    assert resolved["foo"].required_by == ("bar 2.0.0",)


def test_core_gate_rejects_incompatible_eve() -> None:
    cands = [c("future", "1.0.0", eve=">=5.0")]
    with pytest.raises(CoreIncompatibleError, match=r"requires eve '>=5.0'.*running core is 4.0"):
        resolve(cands, CORE)


def test_diamond_conflict_is_hard_error_with_report() -> None:
    cands = [
        c("foo", "1.5.0"),
        c("foo", "2.0.0"),
        c("a", "1.0.0", plugins={"foo": "^1"}),   # >=1,<2
        c("b", "1.0.0", plugins={"foo": ">=2"}),
    ]
    with pytest.raises(DependencyConflictError) as excinfo:
        resolve(cands, CORE)
    report = str(excinfo.value)
    assert "conflict on plugin 'foo'" in report
    assert "a 1.0.0 needs foo ^1" in report
    assert "b 1.0.0 needs foo >=2" in report
    assert "1.5.0, 2.0.0" in report  # available versions listed


def test_unsatisfied_dependency_is_error() -> None:
    cands = [c("a", "1.0.0", plugins={"missing": "^1"})]
    with pytest.raises(DependencyConflictError, match="no source provides plugin 'missing'"):
        resolve(cands, CORE)


def test_exempt_ids_satisfy_dependency_without_a_candidate() -> None:
    # 'ubuntu' is a still-builtin provider (no synced candidate) — exempting it
    # lets a synced package that requires it resolve instead of erroring.
    cands = [c("desktop", "1.0.0", plugins={"ubuntu": ">=1.2"})]
    resolved = {r.id: r.version for r in resolve(cands, CORE, exempt_ids=frozenset({"ubuntu"}))}
    assert resolved == {"desktop": "1.0.0"}
    with pytest.raises(DependencyConflictError, match="no source provides plugin 'ubuntu'"):
        resolve(cands, CORE)


def test_version_from_ref() -> None:
    from eve_sdk.resolver import version_from_ref

    assert version_from_ref("v1.4.0") == "1.4.0"
    assert version_from_ref("2.0") == "2.0"
    assert version_from_ref("main") == "0.0.0"  # non-semver branch/sha


def test_candidate_from_manifest_extracts_requires() -> None:
    manifest = {"id": "pkg", "requires": {"eve": ">=4.0,<5.0", "plugins": {"ubuntu": "^1.2"}}}
    cand = candidate_from_manifest(manifest, "1.1.0", source_id="src")
    assert cand.id == "pkg"
    assert cand.requires_eve == ">=4.0,<5.0"
    assert cand.requires_plugins == {"ubuntu": "^1.2"}
    assert cand.source_id == "src"
