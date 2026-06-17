"""Session setup: hermetic plugin discovery for tests.

Points EVE_PLUGIN_ROOTS at the synthetic test fixtures and (via the session
fixture) sets EVE_PLUGIN_ROOTS_EXCLUSIVE=1 so discovery sees ONLY those
fixtures — no ambient user plugins (.eve/plugins, EVE_HOME) leak into results.
The module-level assignment runs before any eve_sdk import at collection time;
the autouse session fixture pins both vars for the whole run. Tests that need
extra plugins append them to EVE_PLUGIN_ROOTS (exclusive still honours every
listed root).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERMETIC_FIXTURES = str(ROOT / "tests/fixtures/hermetic")

# Set BEFORE any eve_sdk import or fixture runs.
os.environ["EVE_PLUGIN_ROOTS"] = HERMETIC_FIXTURES
os.environ.setdefault("EVE_HOME", tempfile.mkdtemp(prefix="eve-hermetic."))


@pytest.fixture(scope="session", autouse=True)
def _hermetic_plugin_env() -> None:
    """Ensure hermetic plugin discovery for the entire pytest session."""
    os.environ["EVE_PLUGIN_ROOTS"] = HERMETIC_FIXTURES
    os.environ["EVE_PLUGIN_ROOTS_EXCLUSIVE"] = "1"
