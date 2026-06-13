from __future__ import annotations

from eve_sdk import state_machine


def test_normalize_provider_state_aliases() -> None:
    cases = {
        "running": "running",
        "Running": "running",
        "  running  ": "running",
        "stopped": "stopped",
        "not created": "absent",
        "not-created": "absent",
        "absent": "absent",
        "unreachable": "error",
        "failed": "error",
        "": "unknown",
        "  ": "unknown",
        "transitioning": "transitioning",
    }
    for raw, expected in cases.items():
        assert state_machine.normalize_provider_state(raw) == expected


def test_effective_provider_state_recovers_running_error() -> None:
    assert (
        state_machine.effective_provider_state(
            {"provider_state": "error", "desired_state": "running", "provision_state": "provisioned"}
        )
        == "running"
    )
    assert state_machine.effective_provider_state({"provider_state": "error", "desired_state": "stopped"}) == "error"
    assert state_machine.effective_provider_state({}) == "unknown"


def test_live_provider_state_application_rules() -> None:
    running_status = {
        "state": {"provider_state": "running", "desired_state": "running", "provision_state": "provisioned"}
    }
    assert state_machine.should_apply_live_provider_state({"state": {"provider_state": "unknown"}}, "running") is True
    assert state_machine.should_apply_live_provider_state(running_status, "absent") is False
    assert state_machine.should_apply_live_provider_state({"state": {"provider_state": "stopped"}}, "error") is False
    assert state_machine.should_apply_live_provider_state({"state": "not a dict"}, "running") is True
    assert state_machine.should_apply_live_provider_state({"state": {"provider_state": "unknown"}}, "unknown") is False


def test_status_with_provider_state_preserves_inputs_and_clears_resolved_errors() -> None:
    original = {"state": {"provider_state": "unknown", "last_error": "old"}}
    result = state_machine.status_with_provider_state(original, "running")

    assert original["state"]["provider_state"] == "unknown"
    assert result["state"]["provider_state"] == "running"
    assert result["state"]["last_error"] is None
    assert state_machine.status_with_provider_state({"state": "running_string"}, "stopped") == {
        "state": "running_string"
    }
    assert state_machine.status_with_provider_state({"state": None}, "running") == {"state": None}
    assert state_machine.status_with_provider_state({}, "running") == {"state": {"provider_state": "running"}}


def test_status_with_observed_state_merges_and_applies_safe_live_state() -> None:
    result = state_machine.status_with_observed_state(
        {"state": {"provider_state": "unknown"}},
        {"observed_state": {"provider_status": "running", "ip": "1.2.3.4"}},
    )

    assert result["observed_state"]["ip"] == "1.2.3.4"
    assert result["state"]["provider_state"] == "running"
    assert result["state"]["observed_state"]["ip"] == "1.2.3.4"


def test_status_with_observed_state_preserves_local_running_over_absent() -> None:
    result = state_machine.status_with_observed_state(
        {"state": {"provider_state": "running", "desired_state": "running", "provision_state": "provisioned"}},
        {"observed_state": {"provider_status": "absent"}},
    )

    assert result["state"]["provider_state"] == "running"


def test_status_with_observed_state_non_dict_edges() -> None:
    assert state_machine.status_with_observed_state(
        {"state": {"provider_state": "running"}},
        {"observed_state": "not a hash"},
    ) == {"state": {"provider_state": "running"}}
    assert state_machine.status_with_observed_state(
        {"state": "running_string"},
        {"observed_state": {"provider_status": "stopped"}},
    ) == {"state": "running_string", "observed_state": {"provider_status": "stopped"}}
    assert state_machine.status_with_observed_state(
        {"state": None},
        {"observed_state": {"provider_status": "running"}},
    ) == {"state": None, "observed_state": {"provider_status": "running"}}


def test_provider_actions_available() -> None:
    assert state_machine.provider_actions_available({"provider_state": "running"}) is True
    assert state_machine.provider_actions_available({"provider_state": "stopped"}) is False
    assert (
        state_machine.provider_actions_available(
            {"provider_state": "error", "desired_state": "running", "provision_state": "provisioned"}
        )
        is True
    )


def test_aggregate_summary() -> None:
    assert state_machine.aggregate_summary(
        {
            "a": {"state": {"provider_state": "running"}},
            "b": {"state": {"provider_state": "stopped"}},
            "c": {"state": {"provider_state": "absent"}},
            "d": {"state": {"provider_state": "error"}},
            "e": {"state": {"provider_state": "running", "last_error": "boom"}},
            "f": {"state": {"provider_state": "changing"}},
            "g": {"state": "not a dict"},
        }
    ) == {"running": 1, "stopped": 2, "failed": 2, "other": 2}
