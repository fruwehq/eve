"""Local data path contract for Eve.

By default, Eve stores runtime data below the repository root:
`<repo>/.eve/` and `<repo>/.generated/`.

When `EVE_HOME` is set, that directory becomes the parent for both runtime
trees: `<EVE_HOME>/.eve/` and `<EVE_HOME>/.generated/`. Source-tree reads still
use `repo_root()`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar


class Workdir:
    """Single source of truth for Eve repository and runtime paths."""

    _repo_root_override: ClassVar[Path | None] = None
    _root_override: ClassVar[Path | None] = None

    @classmethod
    def reset_overrides(cls) -> None:
        cls._repo_root_override = None
        cls._root_override = None

    @classmethod
    def set_repo_root(cls, path: str | os.PathLike[str]) -> None:
        cls._repo_root_override = cls._expand(path)

    @classmethod
    def set_root(cls, path: str | os.PathLike[str]) -> None:
        cls._root_override = cls._expand(path)

    @classmethod
    def repo_root(cls) -> Path:
        if cls._repo_root_override is not None:
            return cls._repo_root_override
        return Path(__file__).resolve().parents[1]

    @classmethod
    def root(cls) -> Path:
        if cls._root_override is not None:
            return cls._root_override
        eve_home = os.environ.get("EVE_HOME")
        return cls._expand(eve_home) if eve_home else cls.repo_root()

    @classmethod
    def eve_dir(cls) -> Path:
        return cls.root() / ".eve"

    @classmethod
    def generated_dir(cls) -> Path:
        return cls.root() / ".generated"

    @classmethod
    def config_path(cls) -> Path:
        return cls.path_from_env("EVE_CONFIG_PATH", cls.eve_dir() / "config.yaml")

    @classmethod
    def instance_registry_path(cls) -> Path:
        return cls.path_from_env("EVE_INSTANCE_REGISTRY", cls.eve_dir() / "instances.yaml")

    @classmethod
    def plugin_sources_path(cls) -> Path:
        return cls.eve_dir() / "plugin-sources.yaml"

    @classmethod
    def plugins_dir(cls) -> Path:
        return cls.eve_dir() / "plugins"

    @classmethod
    def workdir_base(cls) -> Path:
        return cls.path_from_env("EVE_INSTANCE_WORKDIR", cls.generated_dir() / "instances")

    @classmethod
    def state_base(cls) -> Path:
        return cls.path_from_env("EVE_STATE_DIR", cls.eve_dir() / "state")

    @classmethod
    def instance_workdir(cls, instance_name: str) -> Path:
        return cls.workdir_base() / instance_name

    @classmethod
    def state_path(cls, instance_name: str) -> Path:
        return cls.state_base() / "instances" / f"{instance_name}.json"

    @classmethod
    def overlay_path(cls, instance_name: str) -> Path:
        return cls.instance_workdir(instance_name) / "catalog.local.yaml"

    @classmethod
    def tf_workdir(cls, instance_name: str) -> Path:
        return cls.instance_workdir(instance_name) / "tf"

    @classmethod
    def tf_state_base(cls, instance_name: str) -> Path:
        return cls.tf_workdir(instance_name) / "state"

    @classmethod
    def tf_data_base(cls, instance_name: str) -> Path:
        return cls.tf_workdir(instance_name) / "data"

    @classmethod
    def tf_data_dir(cls, instance_name: str) -> Path:
        return cls.tf_data_base(instance_name) / "default"

    @classmethod
    def logs_dir(cls, instance_name: str) -> Path:
        return cls.instance_workdir(instance_name) / "logs"

    @classmethod
    def uploads_dir(cls, instance_name: str) -> Path:
        return cls.instance_workdir(instance_name) / "uploads"

    @classmethod
    def ensure_dir(cls, path: str | os.PathLike[str]) -> Path:
        expanded = cls._expand(path)
        expanded.mkdir(parents=True, exist_ok=True)
        return expanded

    @classmethod
    def path_from_env(cls, name: str, default_path: str | os.PathLike[str]) -> Path:
        value = os.environ.get(name)
        return cls._expand(value) if value else Path(default_path)

    @classmethod
    def all_paths(cls, instance_name: str) -> dict[str, str]:
        return {
            "INSTANCE_NAME": instance_name,
            "INSTANCE_WORKDIR": str(cls.instance_workdir(instance_name)),
            "INSTANCE_OVERLAY_PATH": str(cls.overlay_path(instance_name)),
            "INSTANCE_STATE_PATH": str(cls.state_path(instance_name)),
            "INSTANCE_TF_WORKDIR": str(cls.tf_workdir(instance_name)),
            "INSTANCE_TF_STATE_BASE": str(cls.tf_state_base(instance_name)),
            "INSTANCE_TF_DATA_BASE": str(cls.tf_data_base(instance_name)),
            "INSTANCE_TF_DATA_DIR": str(cls.tf_data_dir(instance_name)),
        }

    @staticmethod
    def _expand(path: str | os.PathLike[str]) -> Path:
        return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
