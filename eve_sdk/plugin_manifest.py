from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, ClassVar

import yaml

from eve_sdk.schema import validate_json_schema_fragment, validate_schema
from eve_sdk.workdir import Workdir


class PluginManifest:
    API_VERSION = "eve.plugin/v1"
    PROVIDER_COMMANDS: ClassVar[set[str]] = {
        "resolve",
        "init",
        "plan",
        "up",
        "down",
        "start",
        "stop",
        "status",
        "ip",
        "ssh",
        "validate",
    }
    PACKAGE_COMMANDS: ClassVar[set[str]] = {"install", "status", "down"}

    @staticmethod
    def plugin_roots() -> list[Path]:
        roots = [Workdir.repo_root() / "plugins", Workdir.plugins_dir()]
        extra = [
            Path(entry).expanduser().resolve()
            for entry in os.environ.get("EVE_PLUGIN_ROOTS", "").split(":")
            if entry
        ]
        seen: set[Path] = set()
        result: list[Path] = []
        for root in [*roots, *extra]:
            if root not in seen:
                seen.add(root)
                result.append(root)
        return result

    @classmethod
    def plugin_paths(cls) -> list[Path]:
        paths: list[Path] = []
        for root in cls.plugin_roots():
            if root.exists():
                paths.extend(root.glob("**/eve-plugin.yaml"))
        return sorted(paths)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> dict[str, Any]:
        target = Path(path).resolve()
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{target}: manifest must be a mapping")
        loaded["_path"] = str(target)
        loaded["_source"] = "builtin" if str(target).startswith(str(Workdir.repo_root() / "plugins")) else "external"
        return loaded

    @classmethod
    def load_all(cls, kind: str | None = None) -> list[dict[str, Any]]:
        plugins = [cls.load(path) for path in cls.plugin_paths()]
        for plugin in plugins:
            cls.validate(plugin)
        by_key: dict[str, dict[str, Any]] = {}
        for plugin in plugins:
            key = f"{plugin['kind']}:{plugin['id']}"
            if key in by_key and os.environ.get("EVE_PLUGIN_ALLOW_OVERRIDE") != "1":
                raise ValueError(f"duplicate plugin {key}: {by_key[key]['_path']} and {plugin['_path']}")
            by_key[key] = plugin
        result = list(by_key.values())
        if kind:
            result = [plugin for plugin in result if plugin["kind"] == kind]
        return result

    @classmethod
    def validate(cls, plugin: dict[str, Any]) -> None:
        public_manifest = {key: value for key, value in plugin.items() if not key.startswith("_")}
        validate_schema("plugin-manifest.schema.json", public_manifest, "Plugin manifest")
        path = str(plugin.get("_path", "<manifest>"))
        if plugin.get("api_version") != cls.API_VERSION:
            raise ValueError(f"{path}: api_version must be {cls.API_VERSION}")
        kind = plugin.get("kind")
        if kind not in {"provider", "package"}:
            raise ValueError(f"{path}: kind must be provider or package")
        if not re.match(r"^[a-z][a-z0-9-]*$", str(plugin.get("id", ""))):
            raise ValueError(f"{path}: id must match [a-z][a-z0-9-]*")
        commands = plugin.get("commands")
        if not isinstance(commands, dict):
            raise ValueError(f"{path}: commands must be a map")
        required = cls.PROVIDER_COMMANDS if kind == "provider" else cls.PACKAGE_COMMANDS
        missing = sorted(required - set(commands))
        if missing:
            raise ValueError(f"{path}: missing {kind} commands: {', '.join(missing)}")
        cls._validate_command_execs(plugin)
        if kind == "provider" and "config_schema" in plugin:
            config_schema = plugin["config_schema"]
            if not isinstance(config_schema, dict):
                raise ValueError(f"{path}: config_schema must be a map")
            validate_json_schema_fragment(config_schema, f"{path}: config_schema")

    @staticmethod
    def public(plugin: dict[str, Any]) -> dict[str, Any]:
        output = dict(plugin)
        output["path"] = output.pop("_path")
        output["source"] = output.pop("_source")
        return output

    @classmethod
    def _validate_command_execs(cls, plugin: dict[str, Any]) -> None:
        path = Path(str(plugin.get("_path", "")))
        commands = plugin["commands"]
        for name, spec in commands.items():
            if not isinstance(spec, dict):
                raise ValueError(f"{path}: command {name} must be a map")
            exec_path = spec.get("exec")
            if not exec_path:
                raise ValueError(f"{path}: command {name} missing exec")
            candidate = Path(str(exec_path))
            if not candidate.is_absolute():
                plugin_exec = path.parent / candidate
                root_exec = Workdir.repo_root() / candidate
                candidate = plugin_exec if plugin_exec.exists() else root_exec
            if not candidate.is_file():
                raise ValueError(f"{path}: command {name} exec not found: {exec_path}")
