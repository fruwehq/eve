"""Byte-identical parity tripwire for `scripts/catalog-options --json`.

Frozen in Phase 0 commit A before any catalog-decoupling work. Every later
commit (relocation, aggregator, literal removal) must keep this green. If it
fails, the change lost or reshaped catalog data — do not edit the golden to
make it pass; fix the regression.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from eve_sdk.workdir import Workdir

GOLDEN = Workdir.repo_root() / "tests/golden/catalog-options.json"
SCRIPT = Workdir.repo_root() / "scripts/catalog-options"


def _run_catalog_options() -> bytes:
    # Scrub env that could pull in uncommitted synced plugins or an alternate
    # home so the output reflects only the committed tree (config/catalog.yaml
    # + builtin plugins/).
    env = {key: value for key, value in os.environ.items() if key not in {"EVE_PLUGIN_ROOTS", "EVE_HOME"}}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=Workdir.repo_root(),
        env=env,
        check=True,
        capture_output=True,
    )
    return result.stdout


def test_catalog_options_json_matches_golden_byte_for_byte() -> None:
    expected = GOLDEN.read_bytes()
    actual = _run_catalog_options()

    if actual == expected:
        return

    # Structural diff to make a future regression debuggable without weakening
    # the byte-exact assertion above.
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as handle:
        handle.write(actual)
        actual_path = Path(handle.name)
    expected_doc = json.loads(expected)
    actual_doc = json.loads(actual)
    _report_structural_diff(expected_doc, actual_doc)

    raise AssertionError(
        "catalog-options --json drifted from tests/golden/catalog-options.json.\n"
        f"  actual written to: {actual_path}\n"
        "Do not edit the golden to make this pass — fix the regression."
    )


def _report_structural_diff(expected: object, actual: object) -> None:
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        print(f"catalog-options parity: top-level type changed: {type(expected)!r} -> {type(actual)!r}")
        return
    expected_keys = set(expected)
    actual_keys = set(actual)
    if expected_keys != actual_keys:
        print(f"catalog-options parity: top-level keys changed:")
        print(f"  removed: {sorted(expected_keys - actual_keys)}")
        print(f"  added:   {sorted(actual_keys - expected_keys)}")
    for key in sorted(expected_keys & actual_keys):
        expected_len = len(expected[key]) if hasattr(expected[key], "__len__") else None
        actual_len = len(actual[key]) if hasattr(actual[key], "__len__") else None
        if expected_len != actual_len:
            print(f"catalog-options parity: '{key}' length changed: {expected_len} -> {actual_len}")
