"""Locked YAML helpers.

The lock file handle must remain open for the full critical section; callers
must perform reads and writes inside the `with_lock` block.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml


class AtomicYaml:
    @staticmethod
    @contextmanager
    def with_lock(lock_path: str | os.PathLike[str]) -> Iterator[None]:
        path = Path(lock_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            os.chmod(path, 0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def atomic_write(path: str | os.PathLike[str], data: Mapping[str, Any]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=target.parent,
                prefix=".eve-atomic-",
                suffix=".yaml",
                delete=False,
            ) as tmp:
                tmp_name = tmp.name
                yaml.safe_dump(dict(data), tmp, sort_keys=False)
            os.chmod(tmp_name, 0o644)
            os.replace(tmp_name, target)
        except Exception:
            if tmp_name and Path(tmp_name).exists():
                Path(tmp_name).unlink()
            raise

    @staticmethod
    def load_yaml(path: str | os.PathLike[str]) -> dict[str, Any]:
        target = Path(path)
        if not target.exists():
            return {}
        raw = target.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        parsed = yaml.safe_load(raw)
        return parsed if isinstance(parsed, dict) else {}
