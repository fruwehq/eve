"""Command helpers for Eve's Textual UI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, cast

from eve_sdk.engine import default_engine

ROOT = Path(__file__).resolve().parents[1]

_provider_capabilities_cache: dict[str, list[str]] | None = None


def run_command(args: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def instance_rows() -> list[dict[str, Any]]:
    """Concrete instances from the registry, served from the warm Engine.

    Reads the registry in-process (no subprocess, no catalog parse); identical
    shape to ``instance-list --json`` ``instances``.
    """
    rows = default_engine().instance_rows()
    return rows if isinstance(rows, list) else []


def catalog_options() -> dict[str, Any]:
    """Providers/platforms/bundles/packages view, served from the warm Engine.

    Identical shape to ``catalog-options --json``; parsed once per TUI process
    instead of once per refresh.
    """
    return default_engine().catalog_options()


def provider_capabilities_map() -> dict[str, list[str]]:
    """Provider id → sorted capability list, from the warm Engine's plugin set."""
    global _provider_capabilities_cache
    if _provider_capabilities_cache is not None:
        return _provider_capabilities_cache
    result: dict[str, list[str]] = {}
    for plugin in default_engine().plugin_list(kind="provider"):
        plugin_id = str(plugin.get("id", ""))
        capabilities = plugin.get("capabilities", [])
        if isinstance(capabilities, list):
            result[plugin_id] = sorted(str(c) for c in capabilities)
    _provider_capabilities_cache = result
    return result


def provider_has_capability(provider_id: str, capability: str) -> bool:
    return capability in provider_capabilities_map().get(provider_id, [])


def instance_view(instance: str) -> dict[str, Any]:
    """Full instance view, served from the warm Engine (== ``instance-view``)."""
    return default_engine().instance_view(instance)


def instance_observe_view(instance: str) -> dict[str, Any]:
    """Instance view with a fresh live observe first (== ``instance-view --observe``).

    The live ``provider.status`` call is still a subprocess boundary (it shells
    to the provider plugin); the catalog/plugins parse stays warm.
    """
    return default_engine().instance_view(instance, observe=True)


def instance_statuses() -> dict[str, dict[str, Any]]:
    """Last-known status for every instance from one fast in-process sweep.

    Reads persisted state without resolving or live-observing each instance
    (~3-8s each), so the instance table can render real state immediately; the
    selected instance is then live-observed for fresh detail.
    """
    statuses = default_engine().instance_statuses()
    return statuses if isinstance(statuses, dict) else {}


def provider_status_table() -> str:
    code, out, err = run_command(["make", "--no-print-directory", "providers.status"])
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"make providers.status exited {code}")
    return out.strip()


def upload_folders() -> list[str]:
    upload_dir = Path(os.environ.get("EVE_UPLOAD_DIR", ROOT / "upload"))
    if not upload_dir.exists():
        return []
    return sorted(path.name for path in upload_dir.iterdir() if path.is_dir())


def instance_ip(instance: str) -> str:
    code, out, err = run_command(
        ["make", "--no-print-directory", "ip", f"INSTANCE={instance}"],
        env={"EVE_DISABLE_STATE": "1"},
    )
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"make ip exited {code}")
    return out.strip()


def make_args(target: str, instance: str, *extra: str) -> list[str]:
    return ["make", "--no-print-directory", target, f"INSTANCE={instance}", *extra]


def provider_dispatch_args(command: str, instance: str, *extra: str) -> list[str]:
    return [
        str(ROOT / "scripts/provider-dispatch"),
        "--instance",
        instance,
        "--command",
        command,
        *extra,
    ]


def package_make_args(target: str, instance: str, package: str, *extra: str) -> list[str]:
    return ["make", "--no-print-directory", target, f"INSTANCE={instance}", f"PACKAGE={package}", *extra]


def bundle_make_args(target: str, instance: str, bundle: str) -> list[str]:
    return ["make", "--no-print-directory", target, f"INSTANCE={instance}", f"BUNDLE={bundle}"]


PROVIDER_DEBUG_ACTION_IDS = frozenset({"status-details", "plan", "init"})


def provider_pane_data() -> list[dict[str, Any]]:
    """Provider pane rows, from the warm Engine's provider plugin set."""
    plugins = default_engine().plugin_list(kind="provider")
    result: list[dict[str, Any]] = []
    for plugin in plugins:
        plugin_id = str(plugin.get("id", ""))
        display_name = str(plugin.get("display_name") or plugin_id)
        actions: list[dict[str, Any]] = []
        for action in plugin.get("actions", []):
            if not isinstance(action, dict):
                continue
            action_id = str(action.get("id", ""))
            target = str(action.get("target") or "")
            if not target.startswith("provider."):
                continue
            if action_id in PROVIDER_DEBUG_ACTION_IDS:
                continue
            label = str(action.get("label") or action_id)
            actions.append({
                "id": action_id,
                "label": label,
                "target": target,
                "interactive": bool(action.get("interactive")),
            })
        result.append({
            "id": plugin_id,
            "display_name": display_name,
            "actions": actions,
        })
    return sorted(result, key=lambda p: p["id"])


def provider_dispatch_provider_args(provider_id: str, command: str) -> list[str]:
    return [
        str(ROOT / "scripts/provider-dispatch"),
        "--provider",
        provider_id,
        "--command",
        command,
    ]


def create_instance_args(
    name: str,
    platform_choice: dict[str, Any],
    bundles: str,
    packages: str,
    disk_gb: str,
    memory_mb: str,
    provider_ip: str = "",
) -> list[str]:
    args = [
        "make",
        "--no-print-directory",
        "instance.create",
        f"INSTANCE={name}",
        f"MACHINE={platform_choice.get('machine', '')}",
        f"OS={platform_choice.get('os', '')}",
        f"LOCATION={platform_choice.get('location', '')}",
    ]
    if bundles:
        args.append(f"BUNDLES={bundles}")
    if packages:
        args.append(f"PACKAGES={packages}")
    if disk_gb:
        args.append(f"DISK_GB={disk_gb}")
    if memory_mb:
        args.append(f"MEMORY_MB={memory_mb}")
    if provider_ip:
        args.append(f"PROVIDER_IP={provider_ip}")
    return args
