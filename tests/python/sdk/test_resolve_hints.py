"""validate_catalog_selection error hints (v4.2 eve fixes)."""

from __future__ import annotations

import pytest

from eve_sdk.resolve import ResolveError, validate_catalog_selection

_EMPTY = {"machines": [], "oses": [], "inits": [], "locations": []}
_POPULATED = {
    "machines": [{"name": "mock-vm"}],
    "oses": [{"id": "mockos-1.0-amd64"}],
    "inits": [{"id": "ssh-init"}],
    "locations": [{"name": "mock-tokyo"}],
}


def test_empty_catalog_hints_to_pull_plugins() -> None:
    with pytest.raises(ResolveError, match="no plugins are installed yet"):
        validate_catalog_selection(
            _EMPTY, {"machine": "local-qemu-medium"}, None, {}, {}, {}, []
        )


def test_populated_catalog_lists_available_machines() -> None:
    with pytest.raises(ResolveError, match=r"Machine not found: nope \(available: mock-vm\)"):
        validate_catalog_selection(
            _POPULATED, {"machine": "nope"}, None, {"id": "x"}, {"id": "y"}, {"name": "z"}, []
        )


def test_missing_os_hint_on_empty_catalog() -> None:
    with pytest.raises(ResolveError, match="OS not found: foo; no plugins are installed"):
        validate_catalog_selection(
            _EMPTY, {"os": "foo"}, {"name": "m"}, None, {}, {}, []
        )
