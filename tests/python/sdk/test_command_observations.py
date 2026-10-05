from __future__ import annotations

import json

import pytest

from eve_sdk.dispatch import package_status_from_output


@pytest.mark.parametrize("indent", [None, 2])
def test_root_package_status_wins_over_nested_observations(indent: int | None) -> None:
    output = json.dumps({"status": "missing", "packages": [{"status": "installed"}]}, indent=indent)
    assert package_status_from_output(output) == "missing"


@pytest.mark.parametrize("indent", [None, 2])
def test_nested_observations_do_not_supply_a_missing_root_status(indent: int | None) -> None:
    output = json.dumps({"packages": [{"status": "installed"}]}, indent=indent)
    assert package_status_from_output(output) is None


def test_last_root_status_survives_surrounding_command_logs() -> None:
    output = 'starting\n{"status":"missing"}\n{"status":"installed"}\nfinished\n'
    assert package_status_from_output(output) == "installed"
