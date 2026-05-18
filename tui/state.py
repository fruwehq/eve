"""View-state helpers for Eve's Textual UI."""

from __future__ import annotations

import os
from typing import Any

from tui.commands import load_json, provider_has_capability, ROOT


def status_instance_name(status: dict[str, Any] | None) -> str | None:
    if not status:
        return None
    instance = status.get("instance", {})
    if not isinstance(instance, dict):
        return None
    name = instance.get("name")
    return str(name) if name else None


def provider_actions_available(state: dict[str, Any]) -> bool:
    return bool(state.get("provider_actions_available"))


def aggregate_summary() -> dict[str, int]:
    doc = load_json([str(ROOT / "scripts/instance-view"), "--aggregate"])
    return {k: int(v) for k, v in doc.get("aggregate", {}).items()}


def action_allowed_for_instance(action: dict[str, Any], package_id: str, os_family: str) -> bool:
    return True


def password_supported(status: dict[str, Any] | None) -> bool:
    if os.environ.get("EPHEMERAL_WINDOWS_PASSWORD"):
        return status_instance_name(status) is not None
    if not status:
        return False
    instance = status.get("instance", {})
    if not isinstance(instance, dict):
        return False
    provider = str(instance.get("provider") or "")
    return provider_has_capability(provider, "password") and instance.get("os_family") == "windows"
