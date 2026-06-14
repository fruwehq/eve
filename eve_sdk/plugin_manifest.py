from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, ClassVar

import yaml

from eve_sdk.schema import SchemaValidationError, validate_json_schema_fragment, validate_schema
from eve_sdk.semver import SemverError, satisfies
from eve_sdk.workdir import Workdir

CORE_VERSION = "4.0"


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
        path = str(plugin.get("_path", "<manifest>"))
        try:
            validate_schema("plugin-manifest.schema.json", public_manifest, "Plugin manifest")
        except SchemaValidationError as error:
            raise ValueError(cls._compat_schema_error(path, str(error))) from error
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
        if "config_schema" in plugin:
            config_schema = plugin["config_schema"]
            if not isinstance(config_schema, dict):
                raise ValueError(f"{path}: config_schema must be a map")
            validate_json_schema_fragment(config_schema, f"{path}: config_schema")
        cls._validate_requires(plugin, path)

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

    @classmethod
    def _validate_requires(cls, plugin: dict[str, Any], path: str) -> None:
        requires = plugin.get("requires")
        if not isinstance(requires, dict):
            return
        eve_range = requires.get("eve")
        if not isinstance(eve_range, str):
            return
        try:
            ok = satisfies(CORE_VERSION, eve_range)
        except SemverError as error:
            raise ValueError(f"{path}: requires.eve has invalid range {eve_range!r}: {error}") from error
        if not ok:
            raise ValueError(
                f"{path}: requires.eve {eve_range!r} excludes running core version {CORE_VERSION}"
            )

    @staticmethod
    def _compat_schema_error(path: str, message: str) -> str:
        if "/install/ubuntu/steps" in message and "should be non-empty" in message:
            return f"{path}: install.ubuntu.steps must be a non-empty list"
        if "/install/windows/state_files" in message and "is not one of" in message:
            return f"{path}: install.windows.state_files contains unsupported entries"
        if "/install/ubuntu/steps" in message and "is not of type 'string'" in message:
            return f"{path}: install.ubuntu.steps must be a list of strings"
        if "/supports/engines" in message and "is not of type 'array'" in message:
            return f"{path}: supports.engines must be a list"
        if "/supports/os_families" in message and "is not of type 'array'" in message:
            return f"{path}: supports.os_families must be a list"
        return message
