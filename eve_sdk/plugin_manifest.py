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

# Number of times load_all() has actually parsed manifests from disk. The warm
# Engine (eve_sdk.engine) memoizes the result, so a multi-op session should leave
# this at 1 — the Phase 5 "parse once" invariant is asserted against this counter.
LOAD_COUNT = 0


def load_count() -> int:
    """Return how many times load_all() has parsed manifests from disk."""
    return LOAD_COUNT


def reset_load_count() -> None:
    """Reset the disk-parse counter (test helper)."""
    global LOAD_COUNT
    LOAD_COUNT = 0


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
        # When EVE_PLUGIN_ROOTS_EXCLUSIVE=1, return ONLY EVE_PLUGIN_ROOTS paths.
        # This enables hermetic testing: the test suite sets EVE_PLUGIN_ROOTS
        # to a synthetic fixture directory and the flag so no ambient user
        # plugins (.eve/plugins, EVE_HOME) leak into test results.
        if os.environ.get("EVE_PLUGIN_ROOTS_EXCLUSIVE") == "1":
            return [
                Path(entry).expanduser().resolve()
                for entry in os.environ.get("EVE_PLUGIN_ROOTS", "").split(":")
                if entry
            ]
        # repo_root/plugins: legacy builtin location (empty after v4.0 Phase 3).
        # repo_root/.eve/plugins: the eve repo's own pulled first-party plugins,
        #   discoverable regardless of EVE_HOME (so tests that relocate EVE_HOME
        #   still see the default providers/packages).
        # Workdir.plugins_dir(): EVE_HOME-relative synced plugins (the user's).
        roots = [
            Workdir.repo_root() / "plugins",
            Workdir.repo_root() / ".eve" / "plugins",
            Workdir.plugins_dir(),
        ]
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
            if not root.exists():
                continue
            # os.walk(followlinks=True): synced sources are exposed as symlinks
            # under .eve/plugins/<id>; we must descend into them to find manifests.
            # (pathlib's ** symlink-following is 3.13+; this stays 3.12-compatible.)
            for dirpath, _dirs, files in os.walk(root, followlinks=True):
                if "eve-plugin.yaml" in files:
                    paths.append(Path(dirpath) / "eve-plugin.yaml")
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
    def fingerprint(cls) -> tuple[tuple[str, int], ...]:
        """Cheap change-detector for the discovered manifest set.

        A tuple of (path, mtime_ns) over every discovered manifest plus the
        plugins lockfile. The warm Engine compares this between operations to
        decide whether its memoized parse is still valid (e.g. after `eve pull`
        re-materializes plugins under a long-lived TUI session).
        """
        entries: list[tuple[str, int]] = []
        for path in cls.plugin_paths():
            try:
                entries.append((str(path), path.stat().st_mtime_ns))
            except OSError:
                entries.append((str(path), -1))
        lock = Workdir.eve_dir() / "plugins.lock"
        if lock.exists():
            entries.append((str(lock), lock.stat().st_mtime_ns))
        return tuple(entries)

    @classmethod
    def load_all(cls, kind: str | None = None) -> list[dict[str, Any]]:
        global LOAD_COUNT
        LOAD_COUNT += 1
        plugins = [cls.load(path) for path in cls.plugin_paths()]
        for plugin in plugins:
            cls.validate(plugin)
        by_key: dict[str, dict[str, Any]] = {}
        for plugin in plugins:
            key = f"{plugin['kind']}:{plugin['id']}"
            existing = by_key.get(key)
            if existing is not None:
                # Same package id from different sources with DISJOINT supports
                # (e.g. a ubuntu half in eve-packages-linux + a windows half in
                # eve-packages-windows) is the sanctioned dual-OS case: merge the
                # halves back into one record. Anything else is a real duplicate.
                if plugin["kind"] == "package" and cls._supports_disjoint(existing, plugin):
                    by_key[key] = cls._merge_package_halves(existing, plugin)
                    continue
                if os.environ.get("EVE_PLUGIN_ALLOW_OVERRIDE") != "1":
                    raise ValueError(f"duplicate plugin {key}: {existing['_path']} and {plugin['_path']}")
            by_key[key] = plugin
        result = list(by_key.values())
        if kind:
            result = [plugin for plugin in result if plugin["kind"] == kind]
        return result

    @staticmethod
    def _os_families(plugin: dict[str, Any]) -> list[str]:
        raw = plugin.get("supports")
        supports = raw if isinstance(raw, dict) else {}
        fams = supports.get("os_families")
        return [str(f) for f in fams] if isinstance(fams, list) else []

    @classmethod
    def _supports_disjoint(cls, a: dict[str, Any], b: dict[str, Any]) -> bool:
        fa, fb = set(cls._os_families(a)), set(cls._os_families(b))
        return bool(fa) and bool(fb) and fa.isdisjoint(fb)

    @classmethod
    def _merge_package_halves(cls, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        """Merge two disjoint-OS package halves into the whole-manifest equivalent.
        `a` was discovered first (sorted paths → ubuntu/linux before windows), so
        its OS-agnostic fields and ordering win, reproducing the pre-split record.
        `_os_paths` records each OS family's source dir for OS-specific dispatch."""
        merged = dict(a)
        a_fams, b_fams = cls._os_families(a), cls._os_families(b)
        supports = dict(a.get("supports") or {})
        supports["os_families"] = a_fams + [f for f in b_fams if f not in a_fams]
        merged["supports"] = supports
        ai, bi = a.get("install"), b.get("install")
        a_install = ai if isinstance(ai, dict) else {}
        b_install = bi if isinstance(bi, dict) else {}
        if a_install or b_install:
            merged["install"] = {**a_install, **b_install}
        os_paths = dict(a.get("_os_paths") or {fam: a["_path"] for fam in a_fams})
        b_paths = b.get("_os_paths") or {fam: b["_path"] for fam in b_fams}
        os_paths.update(b_paths)
        merged["_os_paths"] = os_paths
        return merged

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
        output = {key: value for key, value in plugin.items() if not key.startswith("_")}
        output["path"] = plugin["_path"]
        output["source"] = plugin["_source"]
        # Per-OS source dirs for a merged dual-OS package (used by the OS-specific
        # provisioner to locate its half's provision tree).
        if "_os_paths" in plugin:
            output["os_paths"] = plugin["_os_paths"]
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
