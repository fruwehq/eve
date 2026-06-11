from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, ClassVar

import yaml

from eve_sdk.workdir import Workdir


class ConfigEnv:
    DEFAULT_CONFIG: ClassVar[Path] = Workdir.repo_root() / "config/defaults.yaml"
    MAPPINGS: ClassVar[list[tuple[tuple[str, str], str]]] = [
        (("aws", "config_file"), "AWS_CONFIG_FILE"),
        (("aws", "profile"), "AWS_PROFILE"),
        (("aws", "region"), "AWS_REGION"),
        (("aws", "shared_credentials_file"), "AWS_SHARED_CREDENTIALS_FILE"),
        (("display", "fps"), "EPHEMERAL_DISPLAY_FPS"),
        (("display", "resolution"), "EPHEMERAL_DISPLAY_RESOLUTION"),
        (("gcp", "application_credentials"), "GOOGLE_APPLICATION_CREDENTIALS"),
        (("gcp", "project"), "GOOGLE_CLOUD_PROJECT"),
        (("gcp", "project"), "GOOGLE_PROJECT"),
        (("global", "my_ip"), "MY_IP"),
        (("global", "provision_user"), "EVE_PROVISION_USER"),
        (("global", "ssh_public_key_file"), "SSH_PUBLIC_KEY_FILE"),
        (("global", "timezone"), "TIMEZONE"),
        (("global", "vm_user_name"), "VM_USER_NAME"),
        (("moonlight", "bitrate_kbps"), "EPHEMERAL_MOONLIGHT_BITRATE_KBPS"),
        (("moonlight", "display_mode"), "EPHEMERAL_MOONLIGHT_DISPLAY_MODE"),
        (("moonlight", "video_codec"), "EPHEMERAL_MOONLIGHT_VIDEO_CODEC"),
        (("moonlight", "video_decoder"), "EPHEMERAL_MOONLIGHT_VIDEO_DECODER"),
        (("raspberry_pi", "hdmi_connector"), "RASPBERRY_PI_HDMI_CONNECTOR"),
        (("raspberry_pi", "hdmi_mode"), "RASPBERRY_PI_HDMI_MODE"),
        (("raspberry_pi", "host"), "RASPBERRY_PI_HOST"),
        (("raspberry_pi", "ip"), "RASPBERRY_PI_IP"),
        (("rdp", "gate_user"), "RDP_GATE_USER"),
        (("rustdesk", "server"), "RUSTDESK_SERVER"),
        (("sunshine", "max_bitrate_kbps"), "SUNSHINE_MAX_BITRATE_KBPS"),
        (("sunshine", "password"), "EPHEMERAL_SUNSHINE_PASSWORD"),
        (("sunshine", "version"), "SUNSHINE_VERSION"),
        (("thinlinc", "accept_eula"), "THINLINC_ACCEPT_EULA"),
        (("thinlinc", "agent_hostname"), "THINLINC_AGENT_HOSTNAME"),
        (("thinlinc", "server_bundle_path"), "THINLINC_SERVER_BUNDLE_PATH"),
        (("thinlinc", "server_bundle_url"), "THINLINC_SERVER_BUNDLE_URL"),
        (("thinlinc", "webaccess_port"), "THINLINC_WEBACCESS_PORT"),
        (("truenas", "api_user"), "TRUENAS_API_USER"),
        (("truenas", "host"), "TRUENAS_HOST"),
        (("truenas", "ssh_host_key_fingerprint"), "TRUENAS_SSH_HOST_KEY_FINGERPRINT"),
        (("truenas", "ssh_port"), "TRUENAS_SSH_PORT"),
        (("truenas", "ssh_private_key_file"), "TRUENAS_SSH_PRIVATE_KEY_FILE"),
        (("truenas", "ssh_user"), "TRUENAS_SSH_USER"),
        (("truenas", "vm_base_dir"), "TRUENAS_VM_BASE_DIR"),
        (("truenas", "vm_pool"), "TRUENAS_VM_POOL"),
        (("truenas", "vm_zvol_prefix"), "TRUENAS_VM_ZVOL_PREFIX"),
        (("vagrant", "show_console"), "VAGRANT_SHOW_CONSOLE"),
    ]
    PATH_ENV_NAMES: ClassVar[set[str]] = {
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "SSH_PUBLIC_KEY_FILE",
        "TRUENAS_SSH_PRIVATE_KEY_FILE",
    }

    @staticmethod
    def load_config(path: str | os.PathLike[str]) -> dict[str, Any]:
        target = Path(path)
        if not target.exists():
            return {}
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{target}: expected a mapping")
        return loaded

    @classmethod
    def merged_config(
        cls,
        default_path: Path | None = None,
        local_path: Path | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        defaults = cls.load_config(default_path or cls.DEFAULT_CONFIG)
        local = cls.load_config(local_path or Workdir.config_path())
        return cls.deep_merge(defaults, local), defaults, local

    @classmethod
    def environment(cls, default_path: Path | None = None, local_path: Path | None = None) -> dict[str, str]:
        config, _defaults, _local = cls.merged_config(default_path, local_path)
        env: dict[str, str] = {}
        for path, name in cls.MAPPINGS:
            value = cls.scalar_value(cls.fetch_path(config, path))
            if value and name in cls.PATH_ENV_NAMES:
                value = cls.normalize_pathish(value)
            if value:
                env[name] = value
        return dict(sorted(env.items()))

    @classmethod
    def structured(
        cls,
        default_path: Path | None = None,
        local_path: Path | None = None,
    ) -> dict[str, dict[str, dict[str, str | None]]]:
        env = cls.environment(default_path, local_path)
        _config, defaults, local = cls.merged_config(default_path, local_path)
        sections: dict[str, dict[str, dict[str, str | None]]] = {}
        for path, name in cls.MAPPINGS:
            section, field = path
            if cls.scalar_value(cls.fetch_path(local, path)):
                source = "config.yaml"
            elif os.environ.get(name):
                source = "env"
            elif cls.scalar_value(cls.fetch_path(defaults, path)):
                source = "default"
            else:
                source = "unset"
            sections.setdefault(section, {})[field] = {"env": name, "value": env.get(name), "source": source}
        return sections

    @staticmethod
    def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(merged.get(key), dict) and isinstance(value, dict):
                merged[key] = ConfigEnv.deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def fetch_path(data: dict[str, Any], path: tuple[str, str]) -> Any:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def scalar_value(value: Any) -> str | None:
        if value is None or value == "":
            return None
        if isinstance(value, (list, dict)):
            raise ValueError(f"structured config values must be scalars, got {type(value).__name__}")
        return str(value)

    @staticmethod
    def normalize_pathish(value: str) -> str:
        home = os.environ["HOME"]
        if value == "~":
            return home
        if value.startswith("~/"):
            return str(Path(home) / value[2:])
        if value == "$HOME":
            return home
        if value.startswith("$HOME/"):
            return f"{home}{value[5:]}"
        if value == "$(HOME)":
            return home
        if value.startswith("$(HOME)/"):
            return f"{home}{value[7:]}"
        return value

    @classmethod
    def emit(cls, fmt: str, default_path: Path | None = None, local_path: Path | None = None) -> str:
        env = cls.environment(default_path, local_path)
        if fmt == "--json":
            return json.dumps(env, indent=2) + "\n"
        if fmt == "--structured":
            return json.dumps(cls.structured(default_path, local_path), indent=2) + "\n"
        if fmt == "--shell":
            return "".join(f"export {key}={shlex.quote(value)}\n" for key, value in env.items())
        if fmt == "--make":
            return "".join(f"{key}={value}\n" for key, value in env.items())
        raise ValueError(f"unsupported config format: {fmt}")
