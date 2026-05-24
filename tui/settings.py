from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


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
    code, stdout, stderr = _run(["./scripts/config-env", "--structured"])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-env failed")
    result: dict[str, dict[str, dict[str, Any]]] = json.loads(stdout)
    return result


def load_provider_schema(provider_id: str) -> dict[str, Any]:
    code, stdout, stderr = _run(["./scripts/plugin-list", "--kind", "provider", "--json"])
    if code != 0:
        raise RuntimeError(stderr.strip() or "plugin-list failed")
    plugins: list[Any] = json.loads(stdout).get("plugins", [])
    for plugin in plugins:
        if plugin.get("id") == provider_id:
            schema: dict[str, Any] = plugin.get("config_schema", {})
            return schema
    return {}


def load_provider_secrets(provider_id: str) -> dict[str, str]:
    code, stdout, stderr = _run([
        "ruby", "-I", "core", "-r", "sdk", "-e",
        'require "sdk"; begin; puts JSON.generate(Eve::SDK::Secrets.read(ARGV[0])); rescue Eve::SDK::Secrets::SecretsError; puts "{}"; end',
        provider_id,
    ])
    if code != 0:
        return {}
    return json.loads(stdout) if stdout.strip() else {}


def load_provider_secret_keys(provider_id: str) -> list[str]:
    code, stdout, _ = _run([
        "ruby", "-I", "core", "-r", "sdk", "-e",
        'require "sdk"; begin; puts Eve::SDK::Secrets.keys_set(ARGV[0]).join("\\n"); rescue Eve::SDK::Secrets::SecretsError; end',
        provider_id,
    ])
    if code != 0 or not stdout.strip():
        return []
    return stdout.strip().split("\n")


def save_provider_secret(provider_id: str, key: str, value: str) -> None:
    env_addition = {"_EVE_SECRET_VALUE": value}
    code, _, stderr = _run_env([
        "ruby", "-I", "core", "-r", "sdk", "-e",
        'require "sdk"; Eve::SDK::Secrets.update(ARGV[0], {ARGV[1] => ENV["_EVE_SECRET_VALUE"]})',
        provider_id,
        key,
    ], extra_env=env_addition)
    if code != 0:
        raise RuntimeError(stderr.strip() or "secret write failed")


def save_value(section: str, field: str, value: str) -> None:
    code, _, stderr = _run(["./scripts/config-save", section, field, value])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-save failed")


def unset_value(section: str, field: str) -> None:
    code, _, stderr = _run(["./scripts/config-save", "--unset", section, field])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-save --unset failed")


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
    "my_ip": "My IP (CIDR)",
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
