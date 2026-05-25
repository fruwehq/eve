from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from eve_sdk.workdir import Workdir

ROOT = Path(__file__).resolve().parents[3]


def test_workdir_all_paths_matches_ruby(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVE_HOME", str(tmp_path))
    env = os.environ | {"EVE_HOME": str(tmp_path)}
    ruby = subprocess.run(
        [
            "ruby",
            "-I",
            str(ROOT / "core"),
            "-r",
            "sdk",
            "-r",
            "json",
            "-e",
            'puts JSON.generate(Eve::SDK::Workdir.all_paths("demo"))',
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    python = json.dumps(Workdir.all_paths("demo"), separators=(",", ":")) + "\n"

    assert python == ruby
