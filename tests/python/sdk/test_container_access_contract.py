"""Container and authenticated guest-access contract regressions."""

from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from eve_sdk.resolve import engine_for, validate_provider_plugin
from eve_sdk.schema import SchemaValidationError, validate_output, validate_schema


def binding() -> dict[str, Any]:
    return {
        "address": "10.201.153.42",
        "credential_reference": {"path": "/explicit/controller-key", "type": "ssh-private-key-file"},
        "host_identity": {"fingerprint": "SHA256:" + "A" * 43, "mechanism": "provider-authenticated-exec"},
        "port": 22,
        "protocol": "ssh",
        "provider_identity": {
            "endpoint": "https://pool:8443",
            "instance_name": "eve-test",
            "owner_id": "a" * 64,
            "project": "eve-ci",
            "provider": "incus",
            "remote": "eve-incus-pool",
        },
        "username": "ubuntu",
        "version": 2,
    }


def observer() -> Any:
    path = Path(__file__).resolve().parents[3] / "scripts/instance-observe"
    loader = importlib.machinery.SourceFileLoader("container_observer", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_container_engine_is_manifest_driven() -> None:
    plugin = {"id": "incus", "kind": "provider", "supports": {"engines": ["incus"], "kinds": ["container"]}}
    machine = {"provider": "incus", "kind": "container"}
    assert engine_for(machine, [plugin]) == "incus"
    assert validate_provider_plugin(machine, "incus", [plugin]) == plugin


@pytest.mark.parametrize("status", ["absent", "creating", "failed", "running", "stopped", "unknown"])
def test_typed_observations_preserve_provider_states(status: str) -> None:
    import json

    access = binding()
    output = {"status": status, "provider_identity": access["provider_identity"]}
    if status == "running":
        output["guest_access"] = access
    validate_output(output, "provider_command_output")
    result = observer().parse_status_output(json.dumps(output))
    assert result["provider_status"] == status
    assert result["provider_identity"] == access["provider_identity"]
    if status == "running":
        assert result["guest_access"] == access
        assert result["ip"] == access["address"]


@pytest.mark.parametrize("field", sorted(binding()))
def test_guest_access_requires_every_typed_field(field: str) -> None:
    access = copy.deepcopy(binding())
    del access[field]
    with pytest.raises(SchemaValidationError):
        validate_output({"status": "running", "guest_access": access}, "provider_command_output")


def test_observed_state_validates_binding_in_cache() -> None:
    state = {
        "instance": "test",
        "desired_state": "running",
        "provider_state": "running",
        "provision_state": "unknown",
        "package_state": {},
        "operation_history": [],
        "observed_state": {"guest_access": binding()},
    }
    validate_schema("observed-state.schema.json", state, "Observation")
    state["observed_state"]["guest_access"]["credential_reference"] = {"raw_private_key": "must-not-be-accepted"}  # type: ignore[index]
    with pytest.raises(SchemaValidationError):
        validate_schema("observed-state.schema.json", state, "Observation")
