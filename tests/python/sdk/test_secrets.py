from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path

import pytest

from eve_sdk.secrets import Secrets, SecretsError


def _secret_worker(secrets_dir: str, index: int) -> None:
    os.environ["EVE_SECRETS_DIR"] = secrets_dir
    Secrets.update("vultr", {f"key_{index}": f"value-{index}"})


def test_secrets_write_read_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_SECRETS_DIR", str(tmp_path))

    Secrets.write("vultr", {"api_key": "secret"})

    assert Secrets.read("vultr") == {"api_key": "secret"}
    assert Secrets.get("vultr", "api_key") == "secret"
    assert Secrets.path_for("vultr").stat().st_mode & 0o777 == 0o600


def test_secrets_update_delete_and_validate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_SECRETS_DIR", str(tmp_path))

    Secrets.write("vultr", {"a": "1", "b": "2"})
    Secrets.update("vultr", {"b": None, "c": "3"})
    Secrets.delete("vultr", ["a"])

    assert Secrets.read("vultr") == {"c": "3"}
    with pytest.raises(SecretsError):
        Secrets.write("vultr", {"bad": 1})  # type: ignore[dict-item]


def test_secrets_concurrent_writers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_SECRETS_DIR", str(tmp_path))
    ctx = mp.get_context("spawn")
    processes = [ctx.Process(target=_secret_worker, args=(str(tmp_path), index)) for index in range(20)]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)

    assert all(process.exitcode == 0 for process in processes)
    assert Secrets.read("vultr") == {f"key_{index}": f"value-{index}" for index in range(20)}
