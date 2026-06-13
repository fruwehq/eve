from __future__ import annotations

from collections.abc import Iterator

import pytest

from eve_sdk.workdir import Workdir


@pytest.fixture(autouse=True)
def reset_workdir_overrides() -> Iterator[None]:
    Workdir.reset_overrides()
    yield
    Workdir.reset_overrides()
