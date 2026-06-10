from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.dispatch import command_vector, run_json, support_allowed
from eve_sdk.workdir import Workdir


class ResolveError(Exception):
    pass


def load_any(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    if target.suffix.lower() == ".json":
        loaded = json.loads(target.read_text(encoding="utf-8"))
    else:
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ResolveError(f"{target}: expected a mapping")
    return loaded


def deep_merge(left: Any, right: Any) -> Any:
    if left is None:
        return right
    if right is None:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            merged[key] = deep_merge(merged.get(key), value)
        return merged
    return right


def merge_by_key(base_arr: Iterable[Any] | None, over_arr: Iterable[Any] | None, key: str) -> list[Any]:
    out = [dict(entry) if isinstance(entry, dict) else entry for entry in (base_arr or [])]
    for entry in over_arr or []:
        if not isinstance(entry, dict):
            continue
        index = next(
            (
                idx
                for idx, candidate in enumerate(out)
                if isinstance(candidate, dict) and candidate.get(key) == entry.get(key)
            ),
            None,
        )
        if index is None:
            out.append(entry)
        else:
            out[index] = deep_merge(out[index], entry)
    return out


def catalog_path() -> Path:
    return Workdir.repo_root() / "config/catalog.yaml"


def local_catalog_path() -> Path:
    value = os.environ.get("EVE_CATALOG_LOCAL")
    return Path(value).expanduser().resolve() if value else Workdir.repo_root() / "config/catalog.local.yaml"


def default_registry_path() -> Path:
    return Workdir.instance_registry_path()


def load_catalog() -> dict[str, Any]:
    base = load_any(catalog_path())
    over = load_any(local_catalog_path())
    merged = deep_merge(base, over)
    for section in ["machines", "oses", "inits", "packages", "bundles", "locations"]:
        key = "id" if section in {"oses", "inits", "packages", "bundles"} else "name"
        merged[section] = merge_by_key(base.get(section), over.get(section), key)
    return merged


def by_key(root: dict[str, Any], section: str, key: str, value: str) -> dict[str, Any] | None:
    for entry in root.get(section, []):
        if isinstance(entry, dict) and entry.get(key) == value:
            return entry
    return None


def provider_plugins() -> list[dict[str, Any]]:
    return run_json(str(Workdir.repo_root() / "scripts/plugin-list"), "--kind", "provider", "--json")["plugins"]


def package_plugins() -> list[dict[str, Any]]:
    return run_json(str(Workdir.repo_root() / "scripts/plugin-list"), "--kind", "package", "--json")["plugins"]


def provider_config_for(instance: dict[str, Any], provider: str) -> dict[str, Any]:
    config = instance.get("provider_config")
    if not isinstance(config, dict):
        return {}
    provider_config = config.get(provider)
    return provider_config if isinstance(provider_config, dict) else config


def validate_provider_metadata(provider_plugin: dict[str, Any], resolved: dict[str, Any]) -> None:
    spec = provider_plugin["commands"]["validate"]
    argv = command_vector(provider_plugin, spec)
    result = subprocess.run(
        argv,
        cwd=Workdir.repo_root(),
        env=os.environ | {"EVE_RESOLVED_JSON": json.dumps(resolved, separators=(",", ":"))},
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return
    message = "\n".join(part for part in [result.stderr.strip(), result.stdout.strip()] if part).strip()
    raise ResolveError(message or f"Provider plugin {provider_plugin['id']} validate failed")


def env_or(name: str, fallback: object) -> str:
    value = os.environ.get(name)
    return value if value else str(fallback)


def env_value(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def resolve_bundle_packages(catalog: dict[str, Any], bundle_ids: list[str]) -> list[str]:
    packages: list[str] = []
    for bundle_id in bundle_ids:
        bundle = by_key(catalog, "bundles", "id", bundle_id)
        if not bundle:
            raise ResolveError(f"Bundle not found: {bundle_id}")
        packages.extend(bundle.get("includes") or [])
    return sorted(set(packages))


def resolve_package_sources(
    catalog: dict[str, Any],
    bundle_ids: list[str],
    direct_packages: list[str],
) -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {}
    for bundle_id in bundle_ids:
        bundle = by_key(catalog, "bundles", "id", bundle_id)
        if not bundle:
            raise ResolveError(f"Bundle not found: {bundle_id}")
        for package_id in bundle.get("includes") or []:
            sources.setdefault(package_id, []).append(f"bundle:{bundle_id}")
    for package_id in direct_packages:
        sources.setdefault(package_id, []).append("direct")
    return {key: sorted(set(value), key=value.index) for key, value in sources.items()}


def init_available_for_provider(init: dict[str, Any], provider: str) -> bool:
    providers = init.get("providers") if isinstance(init.get("providers"), list) else []
    if providers:
        return provider in providers
    return init.get("provider") is None or init.get("provider") == provider


def compatible_inits(
    catalog: dict[str, Any],
    machine: dict[str, Any] | None,
    os_doc: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not machine or not os_doc:
        return []
    provider = machine["provider"]
    candidates = []
    for init in catalog.get("inits", []):
        if not isinstance(init, dict):
            continue
        if init.get("os_family") and init.get("os_family") != os_doc.get("family"):
            continue
        if init_available_for_provider(init, provider):
            candidates.append(init)
    return candidates


def resolve_init(
    catalog: dict[str, Any],
    composition: dict[str, Any],
    machine: dict[str, Any] | None,
    os_doc: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if composition.get("init"):
        return by_key(catalog, "inits", "id", composition["init"])
    candidates = compatible_inits(catalog, machine, os_doc)
    if len(candidates) == 1:
        composition["init"] = candidates[0]["id"]
        return candidates[0]
    if not candidates:
        raise ResolveError(f"No init supports machine {composition.get('machine')} with OS {composition.get('os')}")
    ids = ", ".join(candidate["id"] for candidate in candidates)
    raise ResolveError(
        f"Multiple inits support machine {composition.get('machine')} with OS {composition.get('os')}; "
        f"choose one of: {ids}"
    )


def validate_catalog_selection(
    catalog: dict[str, Any],
    composition: dict[str, Any],
    machine: dict[str, Any] | None,
    os_doc: dict[str, Any] | None,
    init: dict[str, Any] | None,
    location: dict[str, Any] | None,
    bundle_packages: list[str],
) -> None:
    if not machine:
        raise ResolveError(f"Machine not found: {composition.get('machine')}")
    if not os_doc:
        raise ResolveError(f"OS not found: {composition.get('os')}")
    if not init:
        raise ResolveError(f"Init not found: {composition.get('init')}")
    if not location:
        raise ResolveError(f"Location not found: {composition.get('location')}")
    if init.get("os_family") and init.get("os_family") != os_doc.get("family"):
        raise ResolveError(f"Init/OS mismatch: init {init['id']} expects {init['os_family']}, got {os_doc['family']}")
    if not init_available_for_provider(init, machine["provider"]):
        expected = ", ".join(init["providers"]) if isinstance(init.get("providers"), list) else init.get("provider")
        raise ResolveError(
            f"Init/provider mismatch: init {init['id']} expects provider {expected}, "
            f"got machine provider {machine['provider']}"
        )
    provider = machine["provider"]
    if not location.get(provider):
        raise ResolveError(f"Location {location['name']} has no mapping for provider {provider}")
    supports = machine.get("supports") if isinstance(machine.get("supports"), dict) else {}
    if supports.get("arches") and os_doc.get("arch") not in supports["arches"]:
        raise ResolveError(
            f"Machine/OS mismatch: machine {machine['name']} does not support architecture {os_doc.get('arch')}"
        )
    if supports.get("os_ids") and os_doc.get("id") not in supports["os_ids"]:
        raise ResolveError(f"Machine/OS mismatch: machine {machine['name']} does not support OS {os_doc.get('id')}")
    catalog_packages = {pkg.get("id") for pkg in catalog.get("packages", []) if isinstance(pkg, dict)}
    unknown_package = next((pkg for pkg in bundle_packages if pkg not in catalog_packages), None)
    if unknown_package:
        raise ResolveError(f"Bundle references unknown package id: {unknown_package}")


def engine_for(machine: dict[str, Any]) -> str:
    provider = machine["provider"]
    if machine.get("kind") == "metal":
        return "metal"
    if provider == "local-qemu":
        return "qemu"
    if str(provider).startswith("local-"):
        return "vagrant"
    return "terraform"


def validate_provider_plugin(machine: dict[str, Any], engine: str) -> dict[str, Any]:
    provider = machine["provider"]
    plugin = next((entry for entry in provider_plugins() if entry["id"] == provider), None)
    if not plugin:
        raise ResolveError(f"Provider plugin not found: {provider}")
    supports = plugin.get("supports") or {}
    if supports.get("engines") and engine not in supports["engines"]:
        raise ResolveError(f"Provider plugin {provider} does not support engine {engine}")
    machine_kind = machine.get("kind") or "vm"
    if supports.get("kinds") and machine_kind not in supports["kinds"]:
        raise ResolveError(f"Provider plugin {provider} does not support machine kind {machine_kind}")
    return plugin


def resolve_access_value(rule: dict[str, Any], resolved_values: dict[str, str], location: dict[str, Any]) -> str:
    value: object | None = None
    if rule.get("env"):
        value = env_value(rule["env"])
    if (value is None or value == "") and rule.get("value"):
        value = rule["value"]
    if (value is None or value == "") and rule.get("location"):
        value = location.get(rule["location"])
    if (value is None or value == "") and rule.get("fallback"):
        value = resolved_values.get(rule["fallback"])
    return "" if value is None else str(value)


def resolve_access(provider_plugin: dict[str, Any], os_family: str, location: dict[str, Any]) -> dict[str, str]:
    access = provider_plugin.get("access")
    if not isinstance(access, dict):
        raise ResolveError(f"Provider plugin {provider_plugin['id']} has no access rules")
    rules = access.get(os_family) or access.get("default")
    if not isinstance(rules, dict):
        raise ResolveError(f"Provider plugin {provider_plugin['id']} has no access rules for OS family {os_family}")
    resolved: dict[str, str] = {}
    for field in ["bootstrap_user", "provision_user", "human_user"]:
        rule = rules.get(field)
        if not isinstance(rule, dict):
            raise ResolveError(f"Provider plugin {provider_plugin['id']} access.{os_family}.{field} is missing")
        resolved[field] = resolve_access_value(rule, resolved, location)
    return resolved


def validate_package_plugins(bundle_packages: list[str], os_doc: dict[str, Any]) -> None:
    plugins = package_plugins()
    plugin_by_id = {entry["id"]: entry for entry in plugins}
    os_family = os_doc["family"]
    for package_id in bundle_packages:
        plugin = plugin_by_id.get(package_id)
        if not plugin:
            raise ResolveError(f"Package plugin not found: {package_id}")
        supports = plugin.get("supports") or {}
        checks = [
            ("os_families", os_family, "os family"),
            ("arches", os_doc.get("arch", ""), "architecture"),
            ("os_ids", os_doc["id"], "OS"),
            ("os_versions", os_doc.get("version", ""), "OS version"),
            (f"{os_family}_versions", os_doc.get("version", ""), f"{os_family} version"),
        ]
        for field, value, label in checks:
            if not support_allowed(supports, field, value):
                raise ResolveError(f"Package plugin {package_id} does not support {label} {value}")
        conflicts = plugin.get("conflicts_with") if isinstance(plugin.get("conflicts_with"), list) else []
        conflict = next((candidate for candidate in conflicts if candidate in bundle_packages), None)
        if conflict:
            raise ResolveError(f"Package conflict: {package_id} conflicts with {conflict}")
        depends = plugin.get("depends_on") if isinstance(plugin.get("depends_on"), list) else []
        missing = [dep for dep in depends if dep not in bundle_packages]
        if missing:
            raise ResolveError(f"Package {package_id} depends_on {', '.join(missing)} but none are selected")


def order_packages_by_dependency(package_ids: list[str]) -> list[str]:
    plugin_by_id = {entry["id"]: entry for entry in package_plugins()}
    selected = list(package_ids)
    selected_set = set(selected)
    deps = {
        package: [dep for dep in (plugin_by_id.get(package, {}).get("depends_on") or []) if dep in selected_set]
        for package in selected
    }
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(package: str, stack: list[str]) -> None:
        if package in visited:
            return
        if package in visiting:
            raise ResolveError(f"Package dependency cycle: {' -> '.join([*stack, package])}")
        visiting.add(package)
        for dep in deps.get(package, []):
            visit(dep, [*stack, package])
        visiting.remove(package)
        visited.add(package)
        ordered.append(package)

    for package in selected:
        visit(package, [])
    return ordered


def resolve_instance(instance_name: str, registry_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    registry = load_any(registry_path or default_registry_path())
    instance = next(
        (
            entry
            for entry in registry.get("instances", [])
            if isinstance(entry, dict) and entry.get("name") == instance_name
        ),
        None,
    )
    if not instance:
        registry_label = registry_path or default_registry_path()
        raise ResolveError(f"Instance not found: {instance_name} (registry: {registry_label})")
    catalog = load_catalog()
    ignored_keys = {"name", "overrides", "provider_config", "created_at", "updated_at", "state"}
    composition = {key: value for key, value in instance.items() if key not in ignored_keys}
    composition["name"] = instance["name"]
    machine = by_key(catalog, "machines", "name", composition.get("machine", ""))
    os_doc = by_key(catalog, "oses", "id", composition.get("os", ""))
    location = by_key(catalog, "locations", "name", composition.get("location", ""))
    if machine:
        machine = deep_merge(
            machine,
            {"defaults": deep_merge((machine.get("defaults") or {}), instance.get("overrides") or {})},
        )
    init = resolve_init(catalog, composition, machine, os_doc)
    direct_packages = composition.get("packages") or []
    package_sources = resolve_package_sources(catalog, composition.get("bundles") or [], direct_packages)
    bundle_packages = sorted(
        set([*resolve_bundle_packages(catalog, composition.get("bundles") or []), *direct_packages])
    )
    validate_catalog_selection(catalog, composition, machine, os_doc, init, location, bundle_packages)
    assert machine is not None
    assert os_doc is not None
    assert init is not None
    assert location is not None
    provider = machine["provider"]
    provider_config = provider_config_for(instance, provider)
    engine = engine_for(machine)
    provider_plugin = validate_provider_plugin(machine, engine)
    validate_package_plugins(bundle_packages, os_doc)
    bundle_packages = order_packages_by_dependency(bundle_packages)
    resolved = {
        "instance": instance,
        "access": resolve_access(provider_plugin, os_doc["family"], location.get(provider, {})),
        "composition": composition,
        "machine": machine,
        "os": os_doc,
        "init": init,
        "location": location,
        "provider_config": provider_config,
        "bundle_packages": bundle_packages,
        "package_sources": package_sources,
        "provider_plugin": provider,
        "package_plugins": [{"id": package_id, "plugin": package_id} for package_id in bundle_packages],
        "engine": engine,
        "stack_tags": provider,
    }
    validate_provider_metadata(provider_plugin, resolved)
    return resolved


def emit_env(resolved: dict[str, Any]) -> str:
    provider = resolved["machine"]["provider"]
    locp = resolved["location"].get(provider) or {}
    provider_config = resolved.get("provider_config") or {}
    pi_host = (
        provider_config.get("host")
        or provider_config.get("ip")
        or env_or("RASPBERRY_PI_HOST", locp.get("host", ""))
    )
    pi_ip = provider_config.get("ip") or env_or("RASPBERRY_PI_IP", locp.get("ip", ""))
    os_doc = resolved["os"]
    machine_defaults = resolved.get("machine", {}).get("defaults") or {}
    access = resolved["access"]
    lines = {
        "ACCESS_BOOTSTRAP_USER": access["bootstrap_user"],
        "ACCESS_HUMAN_USER": access["human_user"],
        "ACCESS_PROVISION_USER": access["provision_user"],
        "INSTANCE_NAME": resolved["instance"]["name"],
        "PROFILE_NAME": resolved["instance"]["name"],
        "ENGINE": resolved["engine"],
        "PROVIDER": provider,
        "STACK_TAGS": resolved["stack_tags"],
        "LOCATION_NAME": resolved["location"]["name"],
        "OS_ID": os_doc["id"],
        "OS_FAMILY": os_doc["family"],
        "INIT_ID": resolved["init"]["id"],
        "BUNDLE_PACKAGES": ",".join(resolved["bundle_packages"]),
        "VM_MEMORY_MB": str(machine_defaults.get("memory_mb") or 0),
        "VM_CPU_CORES": str(machine_defaults.get("cpu_cores") or machine_defaults.get("cpus") or 0),
        "VM_CPU_MODE": str(machine_defaults.get("cpu_mode") or ""),
        "VM_VCPUS": str(machine_defaults.get("vcpus") or 1),
        "VM_AUTOSTART": str(machine_defaults.get("autostart", True)).lower(),
        "VM_STATE": str(machine_defaults.get("state") or "STOPPED"),
        "VM_NIC_ATTACH": str(machine_defaults.get("network") or locp.get("bridge") or "br0"),
        "VM_DISK_GB": str(machine_defaults.get("disk_gb") or 30),
        "VM_POOL": str(machine_defaults.get("pool") or locp.get("pool") or "main"),
        "VM_PLAN": str(machine_defaults.get("plan") or ""),
        "VM_MACHINE_TYPE": str(machine_defaults.get("machine_type") or ""),
        "VM_DISK_TYPE": str(machine_defaults.get("disk_type") or ""),
        "VM_INSTANCE_TYPE": str(machine_defaults.get("instance_type") or ""),
        "VM_ROOT_VOLUME_TYPE": str(machine_defaults.get("root_volume_type") or ""),
        "GCP_IMAGE_FAMILY": str(os_doc.get("gcp_image_family") or ""),
        "GCP_IMAGE_PROJECT": str(os_doc.get("gcp_image_project") or ""),
        "VULTR_OS_ID": str(os_doc.get("vultr_os_id") or 0),
        "LOCATION_REGION": str(locp.get("region") or ""),
        "LOCATION_AVAILABILITY_ZONE": str(locp.get("availability_zone") or ""),
        "LOCATION_ZONE": str(locp.get("zone") or ""),
        "SSH_USER": access["bootstrap_user"],
        "CLOUD_IMAGE_URL": str(os_doc.get("cloud_image_url") or "") if provider in ("local-qemu", "truenas") else "",
        "HUMAN_USER_NAME": access["human_user"],
        "PROVISION_USER_NAME": access["provision_user"],
        "RASPBERRY_PI_HOST": str(pi_host),
        "RASPBERRY_PI_IP": str(pi_ip),
        "TRUENAS_HOST": env_or("TRUENAS_HOST", locp.get("host", "")),
        "TRUENAS_SSH_PORT": env_or("TRUENAS_SSH_PORT", locp.get("ssh_port", 22)),
        "TRUENAS_SSH_USER": env_or("TRUENAS_SSH_USER", locp.get("ssh_user", "")),
        "VM_USER_NAME": env_or("VM_USER_NAME", ""),
    }
    return "".join(f"{key}={value}\n" for key, value in lines.items())
