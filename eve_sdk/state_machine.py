from __future__ import annotations

import copy
from typing import Any

VALID_LIVE_STATES = {"running", "stopped", "absent", "error"}


def normalize_provider_state(status: Any) -> str:
    normalized = str(status).strip().lower()
    if normalized in {"running", "stopped"}:
        return normalized
    if normalized in {"not created", "not-created", "absent"}:
        return "absent"
    if normalized in {"unreachable", "error", "failed"}:
        return "error"
    return "unknown" if normalized == "" else normalized


def effective_provider_state(state: dict[str, Any]) -> str:
    provider_state = str(state.get("provider_state", "unknown"))
    desired_state = str(state.get("desired_state", "unknown"))
    provision_state = str(state.get("provision_state", "unknown"))
    if provider_state == "error" and desired_state == "running" and provision_state == "provisioned":
        return "running"
    return provider_state


def should_apply_live_provider_state(status: dict[str, Any], live_state: str) -> bool:
    state = status.get("state", {})
    if not isinstance(state, dict):
        return True
    local_state = effective_provider_state(state)
    if live_state == "absent" and local_state == "running":
        return False
    if live_state == "error" and local_state in {"stopped", "absent"}:
        return False
    return live_state in VALID_LIVE_STATES


def status_with_provider_state(status: dict[str, Any], provider_state: str) -> dict[str, Any]:
    result = copy.deepcopy(status)
    state = result.get("state")
    if state is None:
        if "state" in result:
            return result
        result["state"] = {}
        state = result["state"]
    if not isinstance(state, dict):
        return result
    state["provider_state"] = provider_state
    if provider_state in {"running", "stopped", "absent"} and "last_error" in state:
        state["last_error"] = None
    return result


def status_with_observed_state(status: dict[str, Any], state_doc: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(status)
    observed = state_doc.get("observed_state", {})
    if not isinstance(observed, dict):
        return result
    result["observed_state"] = observed
    state = result.get("state")
    if state is None:
        if "state" in result:
            return result
        result["state"] = {}
        state = result["state"]
    if not isinstance(state, dict):
        return result
    state["observed_state"] = observed
    provider_status = str(observed.get("provider_status", ""))
    provider_state = "error" if provider_status == "unreachable" else provider_status
    if provider_state and should_apply_live_provider_state(result, provider_state):
        result = status_with_provider_state(result, provider_state)
    return result


def provider_actions_available(state: dict[str, Any]) -> bool:
    eps = effective_provider_state(state)
    desired_state = str(state.get("desired_state", "unknown"))
    provision_state = str(state.get("provision_state", "unknown"))
    return eps == "running" or (eps == "error" and desired_state == "running" and provision_state == "provisioned")


def aggregate_summary(statuses: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {"running": 0, "stopped": 0, "failed": 0, "other": 0}
    for status in statuses.values():
        state = status.get("state", {})
        if not isinstance(state, dict):
            counts["other"] += 1
            continue
        provider_state = str(state.get("provider_state", "unknown"))
        if state.get("last_error") or provider_state in {"failed", "error"}:
            counts["failed"] += 1
        elif provider_state == "running":
            counts["running"] += 1
        elif provider_state in {"stopped", "absent"}:
            counts["stopped"] += 1
        else:
            counts["other"] += 1
    return counts
