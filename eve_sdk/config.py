from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, ClassVar

import yaml

from eve_sdk.workdir import Workdir


class ConfigEnv:
    """Build the non-secret config→env mapping from core statics + plugin manifests.

    The static ``MAPPINGS`` table carries only TRUE-core rows — sections core
    owns because no provider/package plugin backs them (``global``, ``display``
    the shared display setting, ``vagrant`` the engine, and ``moonlight`` until
    its launcher is extracted (v4.4 §8). Every provider- and
    package-owned row is contributed by that plugin's ``config_schema``
    field-spec ``env_var`` declaration, discovered at runtime across both
    provider and package plugins (``load_all("provider")`` and
    ``load_all("package")``). This keeps core free of provider/package id
    literals and their env-var names.

    Path expansion (~ / $HOME) is carried per-row: core rows flag their own
    path fields, and plugin rows flag every ``type: path`` field. So no
    provider/package env-var name is hard-coded here.

    When no plugins are discoverable (e.g. a fresh clone before ``eve pull``),
    ``load_all`` returns ``[]`` and only the static core rows are emitted —
    correct: no plugin installed ⇒ no provider/package env.
    """

    DEFAULT_CONFIG: ClassVar[Path] = Workdir.repo_root() / "config/defaults.yaml"

    # True-core config→env mappings (no provider/package owns these). Each row
    # is ``((section, field), env_var, is_path)``. Provider and package sections
    # are contributed by their manifests' config_schema. ``is_path`` flags the
    # LOCAL filesystem paths that get ~ / $HOME expansion (remote paths live on
    # the provider host and must not be expanded).
    MAPPINGS: ClassVar[list[tuple[tuple[str, str], str, bool]]] = [
        (("display", "fps"), "EPHEMERAL_DISPLAY_FPS", False),
        (("display", "resolution"), "EPHEMERAL_DISPLAY_RESOLUTION", False),
        (("global", "my_ip"), "MY_IP", False),
        (("global", "provision_user"), "EVE_PROVISION_USER", False),
        (("global", "ssh_public_key_file"), "SSH_PUBLIC_KEY_FILE", True),
        (("global", "timezone"), "TIMEZONE", False),
        (("global", "vm_user_name"), "VM_USER_NAME", False),
        (("vagrant", "show_console"), "VAGRANT_SHOW_CONSOLE", False),
    ]

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

    # ---- plugin-contributed config→env mappings -------------------------- #

    @classmethod
    def _plugin_mappings(
        cls, *, kinds: tuple[str, ...] = ("provider", "package")
    ) -> list[tuple[tuple[str, str], str, bool]]:
        """Plugin-owned config→env rows, declared in each provider/package manifest.

        Scans ``config_schema.config`` for every ``env_var`` declaration (config
        fields are non-secret and always eligible for config-env emission), and
        ``config_schema.secrets`` for ``env_var`` declarations on ``type: path``
        fields only — path-typed secrets (credential files, SSH keys) are local
        file paths the user configures via config.yaml, so they belong in
        config-env output. String-typed secrets (API keys, passwords) are
        injected at dispatch time only and are intentionally excluded.

        Both provider and package plugins are scanned by default (``kinds`` may
        be narrowed), so a package's config fields are emitted from its manifest
        exactly like a provider's. The section is the plugin id; the third tuple
        element is ``is_path`` (``type: path`` fields flag themselves) so values
        get ~ / $HOME expansion without core naming the env var.

        When no plugins are discoverable, returns ``[]`` (clean degradation).
        """
        # Imported lazily so config-env can run on a cold path without pulling
        # the full plugin_manifest validation chain at import time.
        from eve_sdk.plugin_manifest import PluginManifest

        rows: list[tuple[tuple[str, str], str, bool]] = []
        for kind in kinds:
            for plugin in PluginManifest.load_all(kind):
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
                        is_path = spec.get("type") == "path"
                        env_vars = env_var if isinstance(env_var, list) else [env_var]
                        for name in env_vars:
                            rows.append(((plugin["id"], field_name), str(name), is_path))
                # secrets block: only type=path fields (local file paths the
                # user configures, not injected secret values).
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
                            rows.append(((plugin["id"], field_name), str(name), True))
        return rows

    @classmethod
    def _all_mappings(cls) -> list[tuple[tuple[str, str], str, bool]]:
        """Static MAPPINGS + plugin-contributed rows, sorted by (section, field).

        The sort reproduces the alphabetical-by-section order the original
        hardcoded MAPPINGS table had, so ``--structured`` section ordering is
        byte-identical before and after.
        Python's stable sort preserves the env_var order within one field
        (e.g. a plugin that maps one field to two env vars keeps their declared
        order).
        """
        combined = [*cls.MAPPINGS, *cls._plugin_mappings()]
        return sorted(combined, key=lambda row: row[0])

    @classmethod
    def bootstrap_sudo_password(cls, provider_id: str) -> str:
        """Password for first-contact NOPASSWD-sudo setup, declared by the provider.

        A provider manifest names which of its config/secret env vars holds the
        bootstrap password via ``bootstrap.sudo_password_env``; core reads that
        env var generically and never names a provider. Returns "" when the
        provider declares none or the value is unset.
        """
        from eve_sdk.plugin_manifest import PluginManifest

        for plugin in PluginManifest.load_all("provider"):
            if plugin.get("id") != provider_id:
                continue
            bootstrap = plugin.get("bootstrap")
            if isinstance(bootstrap, dict) and bootstrap.get("sudo_password_env"):
                return os.environ.get(str(bootstrap["sudo_password_env"]), "")
        return ""

    @classmethod
    def plugin_provision_env_names(
        cls, *, kinds: tuple[str, ...] = ("provider", "package")
    ) -> list[str]:
        """Every env-var name installed plugins declare — config **and** secrets.

        Provision needs a plugin's full env surface, including the string secrets
        (passwords/keys) that ``_plugin_mappings`` excludes, so each plugin's
        provision steps read their own config + secrets by env var while core
        names none of them. Returns a sorted, de-duped list. When no plugins are
        discoverable, returns ``[]``.
        """
        from eve_sdk.plugin_manifest import PluginManifest

        names: set[str] = set()
        for kind in kinds:
            for plugin in PluginManifest.load_all(kind):
                schema = plugin.get("config_schema") or {}
                if not isinstance(schema, dict):
                    continue
                for block in ("config", "secrets"):
                    fields = schema.get(block)
                    if not isinstance(fields, dict):
                        continue
                    for spec in fields.values():
                        if not isinstance(spec, dict):
                            continue
                        env_var = spec.get("env_var")
                        if not env_var:
                            continue
                        for name in env_var if isinstance(env_var, list) else [env_var]:
                            names.add(str(name))
        return sorted(names)

    @classmethod
    def provision_env_payload(cls, windows_password: str = "") -> dict[str, str]:
        """Build the generic provision ``env.json`` payload (v4.4 §15).

        Core keys (``windows_password``, ``display_resolution``) plus every
        installed *package's* config env that is currently set, keyed by the env
        var name lowercased with an ``EPHEMERAL_`` prefix stripped. Package
        provision steps read their keys (e.g. a streaming host's version, a remote
        …) by construction — core names no package. Unset vars are omitted.
        """
        payload: dict[str, str] = {
            "windows_password": windows_password,
            "display_resolution": os.environ.get("EPHEMERAL_DISPLAY_RESOLUTION", ""),
        }
        for _path, env_var, _is_path in cls._plugin_mappings(kinds=("package",)):
            value = os.environ.get(env_var, "")
            if not value:
                continue
            key = env_var.lower().removeprefix("ephemeral_")
            payload.setdefault(key, value)
        return payload

    @classmethod
    def environment(cls, default_path: Path | None = None, local_path: Path | None = None) -> dict[str, str]:
        config, _defaults, _local = cls.merged_config(default_path, local_path)
        env: dict[str, str] = {}
        for path, name, is_path in cls._all_mappings():
            value = cls.scalar_value(cls.fetch_path(config, path))
            if value and is_path:
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
        for path, name, _is_path in cls._all_mappings():
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
