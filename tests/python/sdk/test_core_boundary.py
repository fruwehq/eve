"""Conformance tests for ``scripts/test-core-boundary`` (Phase 0 commit E).

Asserts the three acceptance criteria:
  1. A clean tree run passes (subprocess exit 0).
  2. A planted provider/OS literal in a scanned core file that is not
     allowlisted is detected as a violation.
  3. The provider/OS id sets are derived dynamically from plugin manifests and
     the aggregated catalog — not hardcoded.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys

import pytest

from eve_sdk.catalog import load_catalog
from eve_sdk.plugin_manifest import PluginManifest
from eve_sdk.workdir import Workdir

REPO = Workdir.repo_root()
SCRIPT = REPO / "scripts/test-core-boundary"


def _load_module():
    """Import the hyphenated script as a module for direct function testing."""
    loader = importlib.machinery.SourceFileLoader("core_boundary", str(SCRIPT))
    spec = importlib.util.spec_from_loader("core_boundary", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_clean_tree_run_passes() -> None:
    """The full check passes on the committed tree (exit 0)."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"EVE_PLUGIN_ROOTS", "EVE_HOME"}
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO,
        env=env,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"[OK]" in result.stdout


def test_self_test_passes() -> None:
    """The --self-test shebang-detection parity check passes."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--self-test"],
        cwd=REPO,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_planted_provider_literal_is_detected() -> None:
    """A provider id in an unallowed scanned core file is a violation."""
    module = _load_module()
    ids = module.all_ids()
    assert "mock-cloud" in ids
    violations = module.find_provider_os_violations(
        [("scripts/some-unallowed-file", 'provider = "mock-cloud"')],
        ids,
        allowed=set(),
    )
    assert len(violations) == 1
    assert "scripts/some-unallowed-file" in violations[0]


def test_planted_os_literal_is_detected() -> None:
    """An OS id in an unallowed scanned core file is a violation."""
    module = _load_module()
    ids = module.all_ids()
    os_id = ids[len(module.provider_ids()):][0]
    violations = module.find_provider_os_violations(
        [("eve_sdk/some_file.py", f'os = "{os_id}"')],
        ids,
        allowed=set(),
    )
    assert len(violations) == 1


def test_allowlisted_literal_is_not_a_violation() -> None:
    """A literal in an allowlisted rel_path is not flagged."""
    module = _load_module()
    ids = module.all_ids()
    violations = module.find_provider_os_violations(
        [("scripts/allowlisted-file", 'provider = "vultr"')],
        ids,
        allowed={"scripts/allowlisted-file"},
    )
    assert violations == []


def test_provider_ids_derived_from_manifests() -> None:
    """Provider ids come from PluginManifest.load_all('provider'), not a literal."""
    module = _load_module()
    expected = sorted(p["id"] for p in PluginManifest.load_all("provider"))
    assert module.provider_ids() == expected
    assert "mock-cloud" in expected


def test_os_ids_derived_from_catalog() -> None:
    """OS ids come from the aggregated catalog oses section, not catalog.yaml grep."""
    module = _load_module()
    expected = sorted(
        entry["id"]
        for entry in load_catalog().get("oses", [])
        if isinstance(entry, dict) and entry.get("id")
    )
    assert module.os_ids() == expected


def test_no_hardcoded_id_list_in_script() -> None:
    """The script source contains no hardcoded PROVIDER_IDS literal list."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "PROVIDER_IDS" not in source
    # The script must not spell out the provider set as a string literal.
    for provider in ("aws", "gcp", "vultr", "truenas"):
        assert f'"{provider}"' not in source, f"hardcoded id {provider!r} in script"


@pytest.mark.parametrize(
    "shebang,detected",
    [
        ("#!/usr/bin/env bash", True),
        ("#!/usr/bin/env sh", True),
        ("#!/bin/bash", True),
        ("#!/bin/sh", True),
        ("#!/usr/bin/env python3", False),
        ("#!/usr/bin/env zsh", False),
    ],
)
def test_shebang_detection(shebang: str, detected: bool) -> None:
    module = _load_module()
    assert module.is_bash_shebang(shebang) is detected
