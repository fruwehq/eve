"""Profile resolution and env/JSON/Vagrant emission for ``scripts/profile-resolve``.

This is a faithful Python port of the legacy bash+jq ``profile-resolve`` script.
The ``--emit env`` stdout contract (the exact ``KEY=value`` lines and their
order) is load-bearing — many already-ported scripts (tf-*, ssh-wait,
wait-for-provision, package-*, remote-*) parse it — so the emission logic below
mirrors the jq ``emit_env`` filter byte-for-byte rather than reusing
``eve_sdk.resolve.emit_env`` (which follows the newer instance-resolve access
rules and emits ``INSTANCE_NAME``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.catalog import load_catalog
from eve_sdk.secrets import Secrets
from eve_sdk.workdir import Workdir

PROFILE_NOT_FOUND_EXIT = 5


class ProfileResolveError(Exception):
    """Resolution error — exit code 5, mirroring ``jq error()`` exit."""


def _jq_coalesce(*values: Any) -> Any:
    """Replicate jq's ``//`` (alternative) operator.

    jq treats ``null`` and ``false`` as falsy; everything else (including ``0``
    and ``""``) is truthy. Returns the first truthy value, or the last value if
    all are falsy.
    """
    for v in values:
        if v is not None and v is not False:
            return v
    return values[-1] if values else None


def _jq_tostring(value: Any) -> str:
    """Replicate jq's ``tostring``: strings pass through; everything else is JSON-encoded."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _env_or(name: str, fallback: Any) -> str:
    """Replicate jq's ``env_or($name; $fallback)``: env var if non-empty, else fallback."""
    value = os.environ.get(name)
    if value:
        return value
    return _jq_tostring(fallback) if not isinstance(fallback, str) else fallback


def _by_key(items: list[Any] | None, key: str, value: str) -> dict[str, Any] | None:
    for entry in items or []:
        if isinstance(entry, dict) and entry.get(key) == value:
            return entry
    return None


def load_catalog_with_profiles() -> dict[str, Any]:
    """Load the aggregated catalog and attach the ``profiles`` section.

    Profiles are a profile-resolve concept not handled by the aggregator; they
    are included from the local overlay or base catalog if present.
    """
    catalog: dict[str, Any] = dict(load_catalog())
    profiles: list[Any] = []
    local_value = os.environ.get("EVE_CATALOG_LOCAL", "")
    for raw_path in [local_value, str(Workdir.repo_root() / "config/catalog.yaml")]:
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(doc, dict) and isinstance(doc.get("profiles"), list):
            profiles = doc["profiles"]
            break
    catalog["profiles"] = profiles
    return catalog


def resolve_profile(catalog: dict[str, Any], profile_name: str) -> dict[str, Any]:
    """Resolve a profile name to the full resolved-object shape.

    Mirrors the jq ``jq_get`` filter: looks up the profile, validates that
    every referenced entity exists, computes ``bundle_packages`` (sorted), and
    determines the engine. Raises ``ProfileResolveError`` (exit 5) on any
    integrity failure.
    """
    profile = _by_key(catalog.get("profiles"), "name", profile_name)
    if profile is None:
        raise ProfileResolveError(f"Profile not found: {profile_name}")

    machine_name = profile.get("machine", "")
    machine = _by_key(catalog.get("machines"), "name", machine_name)
    if machine is None:
        raise ProfileResolveError(f"Machine not found: {machine_name}")

    os_id = profile.get("os", "")
    os_doc = _by_key(catalog.get("oses"), "id", os_id)
    if os_doc is None:
        raise ProfileResolveError(f"OS not found: {os_id}")

    init_id = profile.get("init", "")
    init = _by_key(catalog.get("inits"), "id", init_id)
    if init is None:
        raise ProfileResolveError(f"Init not found: {init_id}")

    location_name = profile.get("location", "")
    location = _by_key(catalog.get("locations"), "name", location_name)
    if location is None:
        raise ProfileResolveError(f"Location not found: {location_name}")

    bundle_ids = profile.get("bundles") or []
    all_bundles = catalog.get("bundles") or []
    bundle_objs = [_by_key(all_bundles, "id", bid) for bid in bundle_ids]
    if any(b is None for b in bundle_objs):
        raise ProfileResolveError(f"One or more bundles not found in profile: {profile.get('name')}")

    direct_packages = profile.get("packages") or []
    bundle_package_lists = [b.get("includes") or [] for b in bundle_objs if b]
    bundle_packages_raw: list[Any] = []
    for pkg_list in bundle_package_lists:
        bundle_packages_raw.extend(pkg_list)
    bundle_packages_raw.extend(direct_packages)
    bundle_packages = sorted(set(bundle_packages_raw))

    package_catalog_ids = {p.get("id") for p in catalog.get("packages") or [] if isinstance(p, dict)}
    for pkg in bundle_packages:
        if pkg not in package_catalog_ids:
            raise ProfileResolveError("Profile references unknown package id")

    init_os_family = init.get("os_family") or ""
    if init_os_family and init_os_family != (os_doc.get("family") or ""):
        raise ProfileResolveError(
            f"Init/OS mismatch: init {init['id']} expects {init_os_family}, "
            f"got OS family {os_doc.get('family')}"
        )

    machine_provider = machine.get("provider") or ""
    init_providers = init.get("providers") if isinstance(init.get("providers"), list) else []
    if init_providers:
        if machine_provider not in init_providers:
            raise ProfileResolveError(
                f"Init/provider mismatch: init {init['id']} expects provider {', '.join(init_providers)}, "
                f"got machine provider {machine_provider}"
            )
    elif init.get("provider") and init.get("provider") != machine_provider:
        raise ProfileResolveError(
            f"Init/provider mismatch: init {init['id']} expects provider {init['provider']}, "
            f"got machine provider {machine_provider}"
        )

    if not location.get(machine_provider):
        raise ProfileResolveError(f"Location {location['name']} has no mapping for provider {machine_provider}")

    machine_kind = machine.get("kind") or ""
    if machine_kind == "metal":
        engine = "metal"
    else:
        # Engine from the provider manifest's supports.engines declaration.
        from eve_sdk.plugin_manifest import PluginManifest

        provider_plugins = PluginManifest.load_all("provider")
        pp = next((p for p in provider_plugins if p["id"] == machine_provider), None)
        engines = ((pp or {}).get("supports") or {}).get("engines") or []
        if engines:
            engine = str(engines[0])
        elif machine_provider.startswith("local-"):
            engine = "vagrant"
        else:
            engine = "terraform"

    return {
        "profile": profile,
        "machine": machine,
        "os": os_doc,
        "init": init,
        "location": location,
        "bundle_packages": bundle_packages,
        "engine": engine,
        "stack_tags": machine_provider,
    }


def adopt_resolved_instance(resolved_json_input: str) -> dict[str, Any]:
    """SDK fast-path: adopt a validated resolved-instance JSON (``EVE_RESOLVED_JSON``).

    The instance-resolve output is a strict superset of this script's resolved
    shape; map ``.instance.name -> .profile.name`` without touching other keys,
    matching the legacy jq remap.
    """
    resolved = json.loads(resolved_json_input)
    if resolved.get("profile") is None:
        instance = resolved.get("instance") or {}
        profile = dict(instance)
        profile["name"] = instance.get("name") or ""
        resolved["profile"] = profile
    return resolved


def apply_provider_secrets(resolved: dict[str, Any]) -> None:
    """Read provider secrets and export them into ``os.environ``.

    Mirrors the bash ``eval "$(python3 ... Secrets.read ...)"`` block: secrets
    already present in the environment are not overridden, and ``None`` values
    are skipped. Applied before emission so that ``env_or`` in ``emit_env``
    picks them up.
    """
    provider = resolved.get("machine", {}).get("provider") or ""
    if not provider:
        return
    for key, value in Secrets.read(provider).items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = str(value)


def emit_env(resolved: dict[str, Any]) -> str:
    """Produce the ``KEY=value`` lines (byte-identical to the legacy jq filter).

    The key order and emission rules (``//`` coalescing, ``env_or``,
    ``provision_user``/``human_user``, ``has()`` for ``use_spot``) are preserved
    exactly. The result ends with a trailing newline.
    """
    provider = resolved["machine"]["provider"]
    locp = resolved["location"].get(provider) or {}
    machine_defaults = resolved.get("machine", {}).get("defaults") or {}
    os_doc = resolved["os"]
    bundle_packages = resolved.get("bundle_packages") or []

    # Resolve provision/human user from the provider manifest's access rules.
    # Profile-resolve only uses the env-var name from the rule (not the full
    # value/location/fallback chain that resolve_access evaluates) — this
    # preserves the legacy emission exactly.
    from eve_sdk.plugin_manifest import PluginManifest

    provider_plugins = PluginManifest.load_all("provider")
    pp = next((p for p in provider_plugins if p["id"] == provider), None)
    os_family = os_doc.get("family") or ""

    def _access_rule(field: str) -> dict[str, Any] | None:
        access = (pp or {}).get("access") or {}
        rules = access.get(os_family) or access.get("default") or {}
        rule = rules.get(field)
        return rule if isinstance(rule, dict) else None

    def _provision_user_value() -> str:
        rule = _access_rule("provision_user")
        if rule and "value" in rule and "env" not in rule:
            return str(rule["value"])  # windows: {value: Administrator}
        env_name = str((rule or {}).get("env") or "VM_USER_NAME")
        return _env_or(env_name, "")

    def _human_user_value() -> str:
        rule = _access_rule("human_user")
        env_name = str((rule or {}).get("env") or "VM_USER_NAME")
        human = _env_or(env_name, "")
        return human if human else _provision_user_value()

    provision_user_value = _provision_user_value()
    human_user_value = _human_user_value()

    # Provider-specific keys from provider-declared env_emission entries.
    from eve_sdk.env_emission import evaluate_provider_env

    provider_env = evaluate_provider_env(resolved, provider_plugins)

    use_spot_value = (
        _jq_tostring(machine_defaults["use_spot"]) if "use_spot" in machine_defaults else ""
    )

    lines: list[tuple[str, str]] = [
        ("ACCESS_BOOTSTRAP_USER", provision_user_value),
        ("ACCESS_HUMAN_USER", human_user_value),
        ("ACCESS_PROVISION_USER", provision_user_value),
        ("PROFILE_NAME", resolved["profile"]["name"]),
        ("ENGINE", resolved["engine"]),
        ("PROVIDER", provider),
        ("STACK_TAGS", resolved["stack_tags"]),
        ("LOCATION_NAME", resolved["location"]["name"]),
        ("OS_ID", os_doc["id"]),
        ("OS_FAMILY", os_doc["family"]),
        ("INIT_ID", resolved["init"]["id"]),
        ("BUNDLE_PACKAGES", ",".join(bundle_packages)),
        ("VM_MEMORY_MB", _jq_tostring(_jq_coalesce(machine_defaults.get("memory_mb"), 0))),
        ("VM_CPU_CORES", _jq_tostring(_jq_coalesce(
            machine_defaults.get("cpu_cores"), machine_defaults.get("cpus"), 0))),
        ("VM_CPU_MODE", _jq_coalesce(machine_defaults.get("cpu_mode"), "")),
        ("VM_VCPUS", _jq_tostring(_jq_coalesce(machine_defaults.get("vcpus"), 1))),
        ("VM_AUTOSTART", _jq_tostring(_jq_coalesce(machine_defaults.get("autostart"), True))),
        ("VM_STATE", _jq_coalesce(machine_defaults.get("state"), "STOPPED")),
        ("VM_NIC_ATTACH", _jq_coalesce(machine_defaults.get("network"), locp.get("bridge"), "br0")),
        ("VM_DISK_GB", _jq_tostring(_jq_coalesce(machine_defaults.get("disk_gb"), 30))),
        ("VM_POOL", _jq_coalesce(machine_defaults.get("pool"), locp.get("pool"), "main")),
        ("VM_PLAN", _jq_coalesce(machine_defaults.get("plan"), "")),
        ("VM_MACHINE_TYPE", _jq_coalesce(machine_defaults.get("machine_type"), "")),
        ("VM_DISK_TYPE", _jq_coalesce(machine_defaults.get("disk_type"), "")),
        ("VM_INSTANCE_TYPE", _jq_coalesce(machine_defaults.get("instance_type"), "")),
        ("VM_ROOT_VOLUME_TYPE", _jq_coalesce(machine_defaults.get("root_volume_type"), "")),
        ("VM_USE_SPOT", use_spot_value),
        ("GCP_IMAGE_FAMILY", provider_env.get("GCP_IMAGE_FAMILY", "")),
        ("GCP_IMAGE_PROJECT", provider_env.get("GCP_IMAGE_PROJECT", "")),
        ("VULTR_OS_ID", provider_env.get("VULTR_OS_ID", "0")),
        ("LOCATION_REGION", _jq_coalesce(locp.get("region"), "")),
        ("LOCATION_AVAILABILITY_ZONE", _jq_coalesce(locp.get("availability_zone"), "")),
        ("LOCATION_ZONE", _jq_coalesce(locp.get("zone"), "")),
        ("SSH_USER", provision_user_value),
        ("CLOUD_IMAGE_URL", provider_env.get("CLOUD_IMAGE_URL", "")),
        ("HUMAN_USER_NAME", human_user_value),
        ("PROVISION_USER_NAME", provision_user_value),
        ("RASPBERRY_PI_HOST", provider_env.get("RASPBERRY_PI_HOST", "")),
        ("RASPBERRY_PI_IP", provider_env.get("RASPBERRY_PI_IP", "")),
        ("TRUENAS_HOST", provider_env.get("TRUENAS_HOST", "")),
        ("TRUENAS_SSH_PORT", provider_env.get("TRUENAS_SSH_PORT", "22")),
        ("TRUENAS_SSH_USER", provider_env.get("TRUENAS_SSH_USER", "")),
        ("VM_USER_NAME", _env_or("VM_USER_NAME", "")),
    ]
    return "".join(f"{key}={value}\n" for key, value in lines)


def emit_json(resolved: dict[str, Any]) -> str:
    """Produce compact JSON (matching ``jq -c``) of the resolved object."""
    return json.dumps(resolved, separators=(",", ":"), ensure_ascii=False)


def emit_vagrant(resolved: dict[str, Any]) -> str:
    """Produce a Vagrantfile for the resolved profile.

    Only ``os.family=ubuntu`` and the ``qemu`` engine are supported;
    any other combination raises ``ProfileResolveError`` (exit 5) — except
    non-ubuntu which exits 2 (usage error), mirroring the legacy guard.
    """
    os_doc = resolved["os"]
    family = os_doc.get("family") or ""
    if family != "ubuntu":
        raise SystemExit(2)

    machine = resolved["machine"]
    engine = resolved.get("engine") or ""
    if engine != "qemu":
        raise ProfileResolveError(f"Vagrant emit only supports the qemu engine, got {engine}")

    defaults = machine.get("defaults") or {}
    bundle_packages = resolved.get("bundle_packages") or []
    name = resolved["profile"]["name"]

    box = _jq_coalesce(os_doc.get("vagrant_box"), "cloud-image/ubuntu-26.04")
    arch = _jq_coalesce(os_doc.get("arch"), "amd64")
    qemu_arch = "aarch64" if arch == "arm64" else "x86_64"
    cpus = _jq_tostring(_jq_coalesce(defaults.get("cpu_cores"), defaults.get("cpus"), 2))
    memory_mb = _jq_coalesce(defaults.get("memory_mb"), 4096)
    qemu_memory = str(int(memory_mb // 1024)) + "G"
    qemu_disk = _jq_tostring(_jq_coalesce(defaults.get("disk_gb"), 30)) + "G"
    pkg_list = " ".join(bundle_packages)

    flags = {"docker": "docker" in bundle_packages, "dev": "dev-toolchain" in bundle_packages}

    port_forwards = ""
    if "sunshine" in bundle_packages:
        port_forwards += (
            '  # Sunshine / Moonlight\n'
            '  config.vm.network "forwarded_port", guest: 47984, host: 47984, auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 47989, host: 47989, auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 47990, host: 47990, auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 48010, host: 48010, auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 47998, host: 47998, protocol: "udp", auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 47999, host: 47999, protocol: "udp", auto_correct: true\n'
            '  config.vm.network "forwarded_port", guest: 48000, host: 48000, protocol: "udp", auto_correct: true\n'
        )
    if "vnc" in bundle_packages:
        port_forwards += (
            '  # VNC\n'
            '  config.vm.network "forwarded_port", guest: 5901, host: 5901, auto_correct: true\n'
        )
    if "xpra" in bundle_packages:
        port_forwards += (
            '  # Xpra\n'
            '  config.vm.network "forwarded_port", guest: 14500, host: 14500, auto_correct: true\n'
        )
    if "rdp" in bundle_packages:
        port_forwards += (
            '  # RDP\n'
            '  config.vm.network "forwarded_port", guest: 3389, host: 3389, auto_correct: true\n'
        )
    if "thinlinc" in bundle_packages:
        port_forwards += (
            '  # ThinLinc Web Access\n'
            '  config.vm.network "forwarded_port", guest: 300, host: 300, auto_correct: true\n'
        )

    docker_setup = ""
    if flags["docker"]:
        docker_setup = (
            '    # Install Docker\n'
            '    sudo install -m 0755 -d /etc/apt/keyrings\n'
            '    curl -fsSL https://download.docker.com/linux/ubuntu/gpg'
            ' | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg\n'
            '    echo "deb [arch=$(dpkg --print-architecture)'
            ' signed-by=/etc/apt/keyrings/docker.gpg]'
            ' https://download.docker.com/linux/ubuntu'
            ' $(. /etc/os-release && echo $VERSION_CODENAME) stable"'
            ' | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null\n'
            '    sudo apt-get update -y\n'
            '    sudo apt-get install -y docker-ce docker-ce-cli containerd.io'
            ' docker-buildx-plugin\n'
            '    sudo usermod -aG docker vagrant\n'
        )

    dev_setup = ""
    if flags["dev"]:
        dev_setup = '    sudo apt-get install -y build-essential pkg-config libssl-dev\n'

    provider_block = (
        f'  config.vm.provider "qemu" do |qe|\n'
        f'    qe.arch = "{qemu_arch}"\n'
        f'    qe.smp = "{cpus}"\n'
        f'    qe.memory = "{qemu_memory}"\n'
        f'    qe.disk_resize = "{qemu_disk}"\n'
        f'  end\n'
    )

    port_sep = "\n" if port_forwards != "" else ""

    return (
        f'Vagrant.configure("2") do |config|\n'
        f'  config.vm.box = "{box}"\n'
        f'  config.vm.box_architecture = "{arch}"\n'
        f'  config.vm.hostname = "{name}"\n'
        f'\n'
        f'{provider_block}'
        f'\n'
        f'{port_forwards}'
        f'{port_sep}'
        f'  config.vm.provision "shell", inline: <<-SHELL\n'
        f'    set -e\n'
        f'    export DEBIAN_FRONTEND=noninteractive\n'
        f'    echo "Bootstrapping profile: {name}"\n'
        f'    echo "Packages: {pkg_list}"\n'
        f'    sudo apt-get update -y\n'
        f'    sudo apt-get install -y curl git jq\n'
        f'{docker_setup}'
        f'{dev_setup}'
        f'  SHELL\n'
        f'end\n'
    )
