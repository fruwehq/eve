from __future__ import annotations

import fcntl
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from eve_sdk.workdir import Workdir


@contextmanager
def registry_lock(registry_path: Path) -> Iterator[None]:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{registry_path}.lock")
    with lock_path.open("a+b") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def registry_path(raw: str | None = None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    env_path = os.environ.get("EVE_INSTANCE_REGISTRY")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Workdir.instance_registry_path()


def load_registry(path: Path, command_name: str) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"{command_name}: registry not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix="eve-registry-",
        suffix=".yaml",
        delete=False,
    ) as tmp:
        tmp_name = tmp.name
        yaml.safe_dump(registry, tmp, sort_keys=False)
    os.replace(tmp_name, path)


def mutate_selection(
    *,
    command_name: str,
    instance_name: str,
    item_id: str,
    action: str,
    field: str,
    registry: dict[str, Any],
) -> None:
    instances = registry.get("instances") or []
    instance = next(
        (entry for entry in instances if isinstance(entry, dict) and entry.get("name") == instance_name),
        None,
    )
    if not instance:
        raise RuntimeError(f"{command_name}: instance not found: {instance_name}")

    items = list(instance.get(field) or [])
    if action == "add":
        items.append(item_id)
    else:
        items = [item for item in items if item != item_id]
    items = sorted(set(items))

    if items:
        instance[field] = items
    else:
        instance.pop(field, None)
    instance["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_registry(root: Path, registry: dict[str, Any], instance_name: str, command_name: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=f"eve-{command_name}-", suffix=".yaml") as tmp:
        yaml.safe_dump(registry, tmp, sort_keys=False)
        tmp.flush()
        result = subprocess.run(
            [str(root / "scripts/instance-resolve"), "--registry", tmp.name, "--instance", instance_name, "--validate"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"{command_name}: updated instance did not validate; registry was not changed")
