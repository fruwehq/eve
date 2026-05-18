"""Command helpers for Eve's Textual UI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

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


def load_json(args: list[str]) -> dict[str, Any]:
    code, out, err = run_command(args)
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"{args[0]} exited {code}")
    parsed = json.loads(out)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{args[0]} did not return a JSON object")
    return cast(dict[str, Any], parsed)


def instance_rows() -> list[dict[str, Any]]:
    doc = load_json([str(ROOT / "scripts/instance-list"), "--json"])
    rows = doc.get("instances", [])
    return rows if isinstance(rows, list) else []


def catalog_options() -> dict[str, Any]:
    return load_json([str(ROOT / "scripts/catalog-options"), "--json"])


def provider_capabilities_map() -> dict[str, list[str]]:
    global _provider_capabilities_cache
    if _provider_capabilities_cache is not None:
        return _provider_capabilities_cache
    doc = load_json([str(ROOT / "scripts/plugin-list"), "--kind", "provider", "--json"])
    result: dict[str, list[str]] = {}
    for plugin in doc.get("plugins", []):
        if not isinstance(plugin, dict):
            continue
        plugin_id = str(plugin.get("id", ""))
        capabilities = plugin.get("capabilities", [])
        if isinstance(capabilities, list):
            result[plugin_id] = sorted(str(c) for c in capabilities)
    _provider_capabilities_cache = result
    return result


def provider_has_capability(provider_id: str, capability: str) -> bool:
    return capability in provider_capabilities_map().get(provider_id, [])


def instance_view(instance: str) -> dict[str, Any]:
    return load_json([str(ROOT / "scripts/instance-view"), "--instance", instance])


def instance_observe_view(instance: str) -> dict[str, Any]:
    return load_json([str(ROOT / "scripts/instance-view"), "--instance", instance, "--observe"])


def provider_status_table() -> str:
    code, out, err = run_command(["make", "--no-print-directory", "providers.status"])
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"make providers.status exited {code}")
    return out.strip()


def upload_folders() -> list[str]:
    upload_dir = Path(os.environ.get("EGAME_UPLOAD_DIR", ROOT / "upload"))
    if not upload_dir.exists():
        return []
    return sorted(path.name for path in upload_dir.iterdir() if path.is_dir())


def instance_ip(instance: str) -> str:
    code, out, err = run_command(
        ["make", "--no-print-directory", "ip", f"INSTANCE={instance}"],
        env={"EGAME_DISABLE_STATE": "1"},
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
