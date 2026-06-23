"""Capability-conflict + port-forward aggregation (v4.4 §8 Phase 4)."""
from __future__ import annotations

from typing import Any

import pytest

from eve_sdk.dispatch import DispatchError, validate_package_support
from eve_sdk.profile_resolve import _aggregate_port_forwards


def test_capability_conflict_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # rustdesk conflicts with session:wayland; a bundle package provides it.
    bundle_plugins = [
        {"id": "rustdesk", "conflicts_capabilities": ["session:wayland"]},
        {"id": "gnome-desktop", "provides": ["session:wayland"]},
    ]
    monkeypatch.setattr(
        "eve_sdk.plugin_manifest.PluginManifest.load_all",
        lambda kind=None: [p for p in bundle_plugins if kind in (None, "package")],
    )
    rustdesk = {"id": "rustdesk", "conflicts_capabilities": ["session:wayland"]}
    resolved = {"os": {"family": "ubuntu", "id": "u", "version": "1", "arch": "amd64"},
                "bundle_packages": ["rustdesk", "gnome-desktop"]}
    with pytest.raises(DispatchError, match="disabled for this bundle"):
        validate_package_support("rustdesk", rustdesk, resolved)


def test_no_conflict_when_capability_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle_plugins = [
        {"id": "rustdesk", "conflicts_capabilities": ["session:wayland"]},
        {"id": "xfce-desktop", "provides": ["session:x11"]},
    ]
    monkeypatch.setattr(
        "eve_sdk.plugin_manifest.PluginManifest.load_all",
        lambda kind=None: bundle_plugins,
    )
    rustdesk = {"id": "rustdesk", "conflicts_capabilities": ["session:wayland"],
                "supports": {"os_families": ["ubuntu"]}}
    resolved = {"os": {"family": "ubuntu", "id": "u", "version": "1", "arch": "amd64"},
                "bundle_packages": ["rustdesk", "xfce-desktop"]}
    validate_package_support("rustdesk", rustdesk, resolved)  # no raise


def test_aggregate_port_forwards(monkeypatch: pytest.MonkeyPatch) -> None:
    plugins = [
        {"id": "sunshine", "vagrant": {"port_forwards": [
            {"guest": 47984, "host": 47984},
            {"guest": 47998, "host": 47998, "protocol": "udp"},
        ]}},
        {"id": "vnc", "vagrant": {"port_forwards": [{"guest": 5901, "host": 5901}]}},
    ]
    monkeypatch.setattr(
        "eve_sdk.plugin_manifest.PluginManifest.load_all",
        lambda kind=None: plugins,
    )
    out = _aggregate_port_forwards(["sunshine", "vnc", "nomachine"])
    assert 'config.vm.network "forwarded_port", guest: 47984, host: 47984, auto_correct: true' in out
    assert 'config.vm.network "forwarded_port", guest: 47998, host: 47998, protocol: "udp", auto_correct: true' in out
    assert 'config.vm.network "forwarded_port", guest: 5901, host: 5901, auto_correct: true' in out
    # a package contributing no ports (nomachine) adds nothing.
    assert "nomachine" not in out


def test_aggregate_port_forwards_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "eve_sdk.plugin_manifest.PluginManifest.load_all",
        lambda kind=None: [],
    )
    assert _aggregate_port_forwards(["anything"]) == ""
