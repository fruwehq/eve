from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, ClassVar

import yaml

from eve_sdk.workdir import Workdir


class ConfigEnv:
    """Build the non-secret config→env mapping from core statics + provider manifests.

    The static ``MAPPINGS`` table carries rows that are NOT provider-owned
    (display, global, moonlight, package sections, etc.). Provider-owned rows
    are contributed by each provider manifest's ``config_schema`` field-spec
    ``env_var`` declarations, discovered at runtime via
    ``PluginManifest.load_all("provider")``. This keeps core free of provider
    id literals.

    When no provider manifests are discoverable (e.g. a fresh clone before
    ``eve pull``), ``load_all`` returns ``[]`` and only the static rows are
    emitted — correct: no provider installed ⇒ no provider env.
    """

    DEFAULT_CONFIG: ClassVar[Path] = Workdir.repo_root() / "config/defaults.yaml"

    # Static non-provider config→env mappings. Provider sections are NOT here —
    # they are contributed by provider manifests' config_schema.
    MAPPINGS: ClassVar[list[tuple[tuple[str, str], str]]] = [
        (("display", "fps"), "EPHEMERAL_DISPLAY_FPS"),
        (("display", "resolution"), "EPHEMERAL_DISPLAY_RESOLUTION"),
        (("global", "my_ip"), "MY_IP"),
        (("global", "provision_user"), "EVE_PROVISION_USER"),
        (("global", "ssh_public_key_file"), "SSH_PUBLIC_KEY_FILE"),
        (("global", "timezone"), "TIMEZONE"),
        (("global", "vm_user_name"), "VM_USER_NAME"),
        (("moonlight", "bitrate_kbps"), "EPHEMERAL_MOONLIGHT_BITRATE_KBPS"),
        (("moonlight", "display_mode"), "EPHEMERAL_MOONLIGHT_DISPLAY_MODE"),
        (("moonlight", "video_codec"), "EPHEMERAL_MOONLIGHT_VIDEO_CODEC"),
        (("moonlight", "video_decoder"), "EPHEMERAL_MOONLIGHT_VIDEO_DECODER"),
        (("nomachine", "version"), "NOMACHINE_VERSION"),
        (("raspberry_pi", "hdmi_connector"), "RASPBERRY_PI_HDMI_CONNECTOR"),
        (("raspberry_pi", "hdmi_mode"), "RASPBERRY_PI_HDMI_MODE"),
        (("raspberry_pi", "host"), "RASPBERRY_PI_HOST"),
        (("raspberry_pi", "ip"), "RASPBERRY_PI_IP"),
        (("rdp", "gate_user"), "RDP_GATE_USER"),
        (("rustdesk", "server"), "RUSTDESK_SERVER"),
        (("splashtop", "email"), "SPLASHTOP_EMAIL"),
        (("splashtop", "streamer_path"), "SPLASHTOP_STREAMER_PATH"),
        (("splashtop", "streamer_url"), "SPLASHTOP_STREAMER_URL"),
        (("sunshine", "max_bitrate_kbps"), "SUNSHINE_MAX_BITRATE_KBPS"),
        (("sunshine", "password"), "EPHEMERAL_SUNSHINE_PASSWORD"),
        (("sunshine", "version"), "SUNSHINE_VERSION"),
        (("thinlinc", "accept_eula"), "THINLINC_ACCEPT_EULA"),
        (("thinlinc", "agent_hostname"), "THINLINC_AGENT_HOSTNAME"),
        (("thinlinc", "server_bundle_path"), "THINLINC_SERVER_BUNDLE_PATH"),
        (("thinlinc", "server_bundle_url"), "THINLINC_SERVER_BUNDLE_URL"),
        (("thinlinc", "webaccess_port"), "THINLINC_WEBACCESS_PORT"),
        (("vagrant", "show_console"), "VAGRANT_SHOW_CONSOLE"),
    ]

    # Env var names whose values get ~/$HOME expansion. These are the LOCAL
    # filesystem paths (AWS config file, GCP credentials, SSH keys, etc.).
    # Remote paths (e.g. TRUENAS_VM_BASE_DIR, which lives on the TrueNAS host)
    # are intentionally NOT here — ~ would expand to the wrong machine.
    # Uppercase env var names do not contain lowercase provider id substrings,
    # so this set does not trip the core-boundary provider-id check.
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

    # ---- provider-contributed config→env mappings ------------------------ #

    @classmethod
    def _provider_mappings(cls) -> list[tuple[tuple[str, str], str]]:
        """Provider-owned config→env rows, declared in each provider manifest.

        Scans ``config_schema.config`` for every ``env_var`` declaration (config
        fields are non-secret and always eligible for config-env emission), and
        ``config_schema.secrets`` for ``env_var`` declarations on ``type: path``
        fields only — path-typed secrets (credential files, SSH keys) are local
        file paths the user configures via config.yaml, so they belong in
        config-env output. String-typed secrets (API keys, passwords) are
        injected at dispatch time only and are intentionally excluded.

        When no providers are discoverable, returns ``[]`` (clean degradation).
        """
        # Imported lazily so config-env can run on a cold path without pulling
        # the full plugin_manifest validation chain at import time.
        from eve_sdk.plugin_manifest import PluginManifest

        rows: list[tuple[tuple[str, str], str]] = []
        for plugin in PluginManifest.load_all("provider"):
            schema = plugin.get("config_schema") or {}
            if not isinstance(schema, dict):
                continue
            # config block: every field with env_var is eligible.
            config_fields = schema.get("config")
            if isinstance(config_fields, dict):
                for field_name, spec in config_fields.items():
                    if not isinstance(spec, dict):
                        continue
                    env_var = spec.get("env_var")
                    if not env_var:
                        continue
                    env_vars = env_var if isinstance(env_var, list) else [env_var]
                    for name in env_vars:
                        rows.append(((plugin["id"], field_name), str(name)))
            # secrets block: only type=path fields (local file paths the user
            # configures, not injected secret values).
            secret_fields = schema.get("secrets")
            if isinstance(secret_fields, dict):
                for field_name, spec in secret_fields.items():
                    if not isinstance(spec, dict):
                        continue
                    if spec.get("type") != "path":
                        continue
                    env_var = spec.get("env_var")
                    if not env_var:
                        continue
                    env_vars = env_var if isinstance(env_var, list) else [env_var]
                    for name in env_vars:
                        rows.append(((plugin["id"], field_name), str(name)))
        return rows

    @classmethod
    def _all_mappings(cls) -> list[tuple[tuple[str, str], str]]:
        """Static MAPPINGS + provider-contributed rows, sorted by (section, field).

        The sort reproduces the alphabetical-by-section order the original
        hardcoded MAPPINGS table had, so ``--structured`` section ordering is
        byte-identical before and after.
        Python's stable sort preserves the env_var order within one field
        (e.g. GCP project → GOOGLE_CLOUD_PROJECT before GOOGLE_PROJECT).
        """
        combined = [*cls.MAPPINGS, *cls._provider_mappings()]
        return sorted(combined, key=lambda row: row[0])

    @classmethod
    def environment(cls, default_path: Path | None = None, local_path: Path | None = None) -> dict[str, str]:
        config, _defaults, _local = cls.merged_config(default_path, local_path)
        env: dict[str, str] = {}
        for path, name in cls._all_mappings():
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
        for path, name in cls._all_mappings():
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
