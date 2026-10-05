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
        "host_identity": {"fingerprint": "SHA256:" + "A" * 43, "mechanism": "incus-authenticated-exec"},
        "port": 22,
        "protocol": "ssh",
        "provider_identity": {
            "provider": "incus",
            "identity": {
                "endpoint": "https://pool:8443",
                "instance_name": "eve-test",
                "owner_id": "a" * 64,
                "project": "eve-ci",
                "remote": "eve-incus-pool",
            },
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
    assert result["provider_status"] == ("unreachable" if status == "failed" else status)
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


def test_invalid_status_cannot_hide_behind_later_valid_ip() -> None:
    with pytest.raises(SchemaValidationError):
        observer().parse_status_output('{"status":"invalid"}\n{"ip":"10.201.153.42"}')


@pytest.mark.parametrize("status", ["absent", "creating", "failed", "stopped", "unknown", "unreachable"])
def test_refresh_replaces_stale_access(tmp_path: Path, monkeypatch: Any, status: str) -> None:
    from eve_sdk.state import State
    from eve_sdk.workdir import Workdir

    monkeypatch.setenv("EVE_HOME", str(tmp_path))
    Workdir.reset_overrides()
    State.update_observed("test-one", {"provider_status": "running", "guest_access": binding(), "ip": "10.201.153.42"})
    state = State.update_observed("test-one", {"provider_status": status})
    assert "guest_access" not in state["observed_state"]
    assert "ip" not in state["observed_state"]


def test_failed_observation_disables_running_provisioned_actions() -> None:
    from eve_sdk.state_machine import effective_provider_state, provider_actions_available, status_with_observed_state

    parsed = observer().parse_status_output('{"status":"failed"}')
    result = status_with_observed_state(
        {"state": {"provider_state": "running", "desired_state": "running", "provision_state": "provisioned"}},
        {"observed_state": parsed},
    )
    assert result["state"]["provider_state"] == "error"
    assert effective_provider_state(result["state"]) == "error"
    assert not provider_actions_available(result["state"])


def test_provider_envelope_and_host_identity_variants_are_closed() -> None:
    access = binding()
    access["username"] = "Administrator"
    access["host_identity"]["mechanism"] = "configured-fingerprint"
    validate_output(access, "guest_access")
    access["provider_identity"]["identity"]["opaque"] = "not allowed"
    with pytest.raises(SchemaValidationError):
        validate_output(access, "guest_access")


def test_shared_access_definitions_match() -> None:
    from eve_sdk.schema import load_schema

    output = load_schema("command-io.schema.json")["$defs"]
    cache = load_schema("observed-state.schema.json")["$defs"]
    for definition in ("guest_access", "incus_identity", "provider_identity"):
        assert output[definition] == cache[definition]


def test_failed_refresh_removes_binding_even_with_running_status(tmp_path: Path, monkeypatch: Any) -> None:
    from eve_sdk.state import State

    monkeypatch.setenv("EVE_HOME", str(tmp_path))
    State.update_observed("test-one", {"provider_status": "running", "guest_access": binding(), "ip": "10.201.153.42"})
    state = State.update_observed("test-one", {"provider_status": "running", "refresh_error": "timeout"})
    assert "guest_access" not in state["observed_state"]
    assert "ip" not in state["observed_state"]
