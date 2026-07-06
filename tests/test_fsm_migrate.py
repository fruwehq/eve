"""Persisted-state vocabulary migration (eve_sdk.fsm_migrate)."""

from __future__ import annotations

from eve_sdk.fsm_migrate import migrate_state_doc


def test_stable_values_are_identity() -> None:
    doc = {
        "provider_state": "running",
        "provision_state": "provisioned",
        "package_state": {"pkg": {"status": "installed", "at": "t"}},
    }
    out = migrate_state_doc(doc)
    assert out["provider_state"] == "running"
    assert out["provision_state"] == "provisioned"
    assert out["package_state"]["pkg"] == {"status": "installed", "at": "t"}


def test_renamed_values() -> None:
    out = migrate_state_doc(
        {
            "provider_state": "changing",       # terraform micro-stage -> re-observe
            "provision_state": "unknown",
            "package_state": {"pkg": {"status": "reinstalled"}},
        }
    )
    assert out["provider_state"] == "unknown"
    assert out["provision_state"] == "unprovisioned"
    assert out["package_state"]["pkg"]["status"] == "installed"


def test_error_maps_per_region() -> None:
    assert migrate_state_doc({"provider_state": "error"})["provider_state"] == "error"
    assert migrate_state_doc({"provision_state": "error"})["provision_state"] == "provision_error"


def test_other_fields_and_idempotence() -> None:
    doc = {"provider_state": "changing", "desired_state": "running", "name": "vm1"}
    once = migrate_state_doc(doc)
    assert once["desired_state"] == "running" and once["name"] == "vm1"
    assert migrate_state_doc(once) == once  # idempotent
