from __future__ import annotations

import json
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


def load_structured() -> dict[str, dict[str, dict[str, Any]]]:
    code, stdout, stderr = _run(["./scripts/config-env", "--structured"])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-env failed")
    result: dict[str, dict[str, dict[str, Any]]] = json.loads(stdout)
    return result


def save_value(section: str, field: str, value: str) -> None:
    code, _, stderr = _run(["./scripts/config-save", section, field, value])
    if code != 0:
        raise RuntimeError(stderr.strip() or "config-save failed")


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
