from __future__ import annotations

from eve_sdk import state_machine


def test_state_machine_normalization() -> None:
    assert state_machine.normalize_provider_state("not created") == "absent"
    assert state_machine.normalize_provider_state("unreachable") == "error"
    assert state_machine.normalize_provider_state("  ") == "unknown"


def test_state_machine_observed_state_does_not_downgrade_running_to_absent() -> None:
    result = state_machine.status_with_observed_state(
        {"state": {"provider_state": "running", "desired_state": "running", "provision_state": "provisioned"}},
        {"observed_state": {"provider_status": "absent"}},
    )

    assert result["state"]["provider_state"] == "running"


def test_state_machine_summary() -> None:
    assert state_machine.aggregate_summary(
        {
            "a": {"state": {"provider_state": "running"}},
            "b": {"state": {"provider_state": "stopped"}},
            "c": {"state": {"provider_state": "error"}},
            "d": {"state": {"provider_state": "changing"}},
        }
    ) == {"running": 1, "stopped": 1, "failed": 1, "other": 1}
