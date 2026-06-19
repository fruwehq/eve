from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, cast

from eve_sdk.engine import default_engine
from eve_sdk.secrets import Secrets, SecretsError


_CACHE_TTL = 5.0
_cache: dict[tuple[str, tuple[str, ...]], tuple[float, Any]] = {}


def _invalidate_cache() -> None:
    keys_to_remove = [k for k in _cache if k[0] in ("load_structured", "load_provider_schema")]
    for k in keys_to_remove:
        del _cache[k]


def root_dir() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _run(args: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 1, "", "command timed out"


def _run_env(args: list[str], extra_env: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = {**os.environ, **(extra_env or {})}
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, env=env)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return 1, "", "command timed out"


def load_structured() -> dict[str, dict[str, dict[str, Any]]]:
    cache_key = ("load_structured", ())
    now = time.monotonic()
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cast("dict[str, dict[str, dict[str, Any]]]", cached)
    code, stdout, stderr = _run(["./scripts/config-env", "--structured"])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-env failed")
    result: dict[str, dict[str, dict[str, Any]]] = json.loads(stdout)
    _cache[cache_key] = (now, result)
    return result


def load_provider_schema(provider_id: str) -> dict[str, Any]:
    """Provider ``config_schema``, served from the warm Engine's plugin set.

    Subprocess-ing ``plugin-list`` per settings-screen open re-parsed every
    provider manifest; the Engine memoizes them once per TUI process. The 5s
    TTL cache is preserved so repeated opens stay instant.
    """
    cache_key = ("load_provider_schema", (provider_id,))
    now = time.monotonic()
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cast("dict[str, Any]", cached)
    for plugin in default_engine().plugin_list(kind="provider"):
        if plugin.get("id") == provider_id:
            schema: dict[str, Any] = plugin.get("config_schema", {})
            _cache[cache_key] = (now, schema)
            return schema
    _cache[cache_key] = (now, {})
    return {}


def load_provider_secrets(provider_id: str) -> dict[str, str]:
    try:
        return Secrets.read(provider_id)
    except SecretsError:
        return {}


def load_provider_secret_keys(provider_id: str) -> list[str]:
    try:
        return Secrets.keys_set(provider_id)
    except SecretsError:
        return []


def save_provider_secret(provider_id: str, key: str, value: str) -> None:
    try:
        Secrets.update(provider_id, {key: value})
    except SecretsError as error:
        raise RuntimeError(str(error) or "secret write failed") from error
    _invalidate_cache()


def save_value(section: str, field: str, value: str) -> None:
    code, _, stderr = _run(["./scripts/config-save", section, field, value])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-save failed")
    _invalidate_cache()


def unset_value(section: str, field: str) -> None:
    code, _, stderr = _run(["./scripts/config-save", "--unset", section, field])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-save --unset failed")
    _invalidate_cache()


def load_missing_fields() -> list[dict[str, Any]]:
    code, stdout, _ = _run(["./scripts/check-required", "--json"])
    if not stdout.strip():
        return []
    try:
        result: list[dict[str, Any]] = json.loads(stdout).get("missing", [])
        return result
    except (json.JSONDecodeError, ValueError):
        return []


CONFIG_SECTIONS: list[dict[str, str]] = [
    {"id": "global", "label": "Global"},
    {"id": "display", "label": "Display"},
    {"id": "moonlight", "label": "Moonlight"},
    {"id": "sunshine", "label": "Sunshine"},
    {"id": "rdp", "label": "RDP"},
    {"id": "rustdesk", "label": "RustDesk"},
    {"id": "thinlinc", "label": "ThinLinc"},
    {"id": "aws", "label": "AWS"},
    {"id": "gcp", "label": "GCP"},
    {"id": "truenas", "label": "TrueNAS"},
    {"id": "raspberry_pi", "label": "Raspberry Pi"},
    {"id": "vagrant", "label": "Vagrant"},
]

FIELD_LABELS: dict[str, str] = {
    "vm_user_name": "VM Username",
    "my_ip": "My IP",
    "ssh_public_key_file": "SSH Public Key",
    "timezone": "Timezone",
    "provision_user": "Provision User",
    "fps": "FPS",
    "resolution": "Resolution",
    "bitrate_kbps": "Bitrate (Kbps)",
    "display_mode": "Display Mode",
    "video_codec": "Video Codec",
    "video_decoder": "Video Decoder",
    "max_bitrate_kbps": "Max Bitrate (Kbps)",
    "version": "Version",
    "gate_user": "Gate User",
    "server": "Server",
    "accept_eula": "Accept EULA",
    "agent_hostname": "Agent Hostname",
    "server_bundle_path": "Bundle Path",
    "server_bundle_url": "Bundle URL",
    "webaccess_port": "Web Access Port",
    "config_file": "Config File",
    "profile": "Profile",
    "region": "Region",
    "shared_credentials_file": "Credentials File",
    "application_credentials": "App Credentials",
    "project": "Project",
    "host": "Host",
    "api_user": "API User",
    "ssh_host_key_fingerprint": "SSH Host Key",
    "ssh_port": "SSH Port",
    "ssh_private_key_file": "SSH Private Key",
    "ssh_user": "SSH User",
    "vm_base_dir": "VM Base Dir",
    "vm_pool": "VM Pool",
    "vm_zvol_prefix": "ZVol Prefix",
    "hdmi_connector": "HDMI Connector",
    "hdmi_mode": "HDMI Mode",
    "ip": "IP Address",
    "show_console": "Show Console",
}


def field_label(section_id: str, field_id: str) -> str:
    return FIELD_LABELS.get(field_id, field_id.replace("_", " ").title())


# Description + example for the static (non-provider) config fields. Provider
# fields (aws/gcp/truenas) carry their own description/default in the plugin
# manifest's config_schema; these cover the core sections the manifest can't.
# Keyed "<section>.<field>".
FIELD_META: dict[str, dict[str, str]] = {
    "global.my_ip": {
        "description": "Your public IPv4 address — used to allow inbound SSH to cloud VMs "
        "(a /32 CIDR is appended automatically, so enter a plain IP).",
        "example": "203.0.113.42",
    },
    "global.provision_user": {
        "description": "User that runs provisioning over SSH. Defaults to the provider's "
        "bootstrap user when unset.",
        "example": "ubuntu",
    },
    "global.ssh_public_key_file": {
        "description": "Path to the SSH public key injected into new VMs for access.",
        "example": "~/.ssh/id_ed25519.pub",
    },
    "global.timezone": {
        "description": "IANA timezone applied inside provisioned VMs.",
        "example": "Europe/Berlin",
    },
    "global.vm_user_name": {
        "description": "Login user created on the VM; overrides the provider's default "
        "access user.",
        "example": "chris",
    },
    "display.fps": {
        "description": "Target frames per second for the remote desktop stream.",
        "example": "60",
    },
    "display.resolution": {
        "description": "Remote desktop resolution, WIDTHxHEIGHT.",
        "example": "2560x1440",
    },
    "moonlight.bitrate_kbps": {
        "description": "Moonlight client streaming bitrate, in kilobits per second.",
        "example": "20000",
    },
    "moonlight.display_mode": {
        "description": "Moonlight window mode.",
        "example": "fullscreen | borderless | windowed",
    },
    "moonlight.video_codec": {
        "description": "Preferred Moonlight video codec.",
        "example": "auto | H.264 | HEVC | AV1",
    },
    "moonlight.video_decoder": {
        "description": "Moonlight video decoder selection.",
        "example": "auto | hardware | software",
    },
    "sunshine.max_bitrate_kbps": {
        "description": "Maximum Sunshine host streaming bitrate, in kilobits per second.",
        "example": "50000",
    },
    "sunshine.password": {
        "description": "Password for the Sunshine web UI / Moonlight pairing flow.",
        "example": "",
    },
    "sunshine.version": {
        "description": "Sunshine version to install (pinned).",
        "example": "2025.924.154138",
    },
    "rdp.gate_user": {
        "description": "Username for the RDP gateway login on GNOME desktops.",
        "example": "rdpuser",
    },
    "rustdesk.server": {
        "description": "RustDesk relay/ID server address. Leave unset to use the public servers.",
        "example": "rustdesk.example.com",
    },
    "thinlinc.accept_eula": {
        "description": "Set to 1 to accept the ThinLinc server EULA during install.",
        "example": "1",
    },
    "thinlinc.agent_hostname": {
        "description": "Hostname the ThinLinc agent advertises to clients.",
        "example": "vm.example.com",
    },
    "thinlinc.server_bundle_path": {
        "description": "Local path to a downloaded ThinLinc server bundle.",
        "example": "~/Downloads/thinlinc-server.zip",
    },
    "thinlinc.server_bundle_url": {
        "description": "URL to download the ThinLinc server bundle from.",
        "example": "https://example.com/thinlinc-server.zip",
    },
    "thinlinc.webaccess_port": {
        "description": "Port for ThinLinc Web Access.",
        "example": "300",
    },
    "raspberry_pi.hdmi_connector": {
        "description": "Which HDMI connector to force output on.",
        "example": "0 | 1",
    },
    "raspberry_pi.hdmi_mode": {
        "description": "Forced HDMI display mode.",
        "example": "1920x1080@60",
    },
    "raspberry_pi.host": {
        "description": "SSH hostname of the Raspberry Pi.",
        "example": "raspberrypi.local",
    },
    "raspberry_pi.ip": {
        "description": "IP address of the Raspberry Pi.",
        "example": "192.168.1.50",
    },
    "vagrant.show_console": {
        "description": "Show the VM console window when starting a local Vagrant VM.",
        "example": "1",
    },
}


def field_meta(section_id: str, field_id: str) -> dict[str, str]:
    """Static description/example for a config field (``{}`` when unknown)."""
    return FIELD_META.get(f"{section_id}.{field_id}", {})
