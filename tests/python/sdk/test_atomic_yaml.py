from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from eve_sdk.atomic_yaml import AtomicYaml


def _atomic_worker(root: str, index: int) -> None:
    path = Path(root) / "data.yaml"
    lock = Path(root) / "data.lock"
    with AtomicYaml.with_lock(lock):
        data = AtomicYaml.load_yaml(path)
        data[f"key_{index}"] = index
        AtomicYaml.atomic_write(path, data)


def test_atomic_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"

    AtomicYaml.atomic_write(path, {"root": {"value": "ok"}})

    assert AtomicYaml.load_yaml(path) == {"root": {"value": "ok"}}
    assert path.stat().st_mode & 0o777 == 0o644


def test_atomic_yaml_concurrent_writers(tmp_path: Path) -> None:
    ctx = mp.get_context("spawn")
    processes = [ctx.Process(target=_atomic_worker, args=(str(tmp_path), index)) for index in range(20)]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)

    assert all(process.exitcode == 0 for process in processes)
    assert AtomicYaml.load_yaml(tmp_path / "data.yaml") == {f"key_{index}": index for index in range(20)}
