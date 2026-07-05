"""The core instance and package machines (core/fsm/*.yaml) over the Determa State engine.

Loading each machine runs it through the engine's static validation (reachable states,
no dead branches); the tests then exercise the key lifecycle transitions that replace
state.py's PROVIDER_STATES / PROVISION_STATES / PACKAGE_STATES.
"""

from __future__ import annotations

from pathlib import Path

from eve_sdk.fsm import EveFsm

CORE = Path(__file__).resolve().parents[1] / "core" / "fsm"


def _fsm(scope: str, external: dict[str, str] | None = None) -> EveFsm:
    ext = dict(external or {})
    fsm = EveFsm(lambda s, k, names: {n: ext.get(n, "") for n in names})
    fsm.load(scope, (CORE / f"{scope}.yaml").read_text())
    return fsm


def _leaves(fsm: EveFsm, scope: str, key: str = "x") -> list[str]:
    return sorted(fsm.instance(scope, key).active_leaf_names())


def test_package_lifecycle() -> None:
    fsm = _fsm("package")
    assert _leaves(fsm, "package") == ["unknown"]

    fsm.fire("package", "x", "absent")
    assert _leaves(fsm, "package") == ["missing"]

    fsm.fire("package", "x", "install")
    assert _leaves(fsm, "package") == ["installing"]

    fsm.fire("package", "x", "install_fail")
    assert _leaves(fsm, "package") == ["failed"]

    fsm.fire("package", "x", "install")           # retry
    fsm.fire("package", "x", "install_ok")
    assert _leaves(fsm, "package") == ["installed"]

    fsm.fire("package", "x", "absent")            # drift: disappeared out of band
    assert _leaves(fsm, "package") == ["missing"]


def test_instance_regions_advance_independently() -> None:
    fsm = _fsm("instance", {"desired": "running"})
    assert _leaves(fsm, "instance") == ["absent", "unprovisioned"]

    fsm.fire("instance", "x", "create")
    fsm.fire("instance", "x", "created_ok")
    assert _leaves(fsm, "instance") == ["running", "unprovisioned"]

    # the provisioning region advances without touching the provider region
    fsm.fire("instance", "x", "provision")
    fsm.fire("instance", "x", "provision_ok")
    assert _leaves(fsm, "instance") == ["provisioned", "running"]

    # stop lands in stopped; destroy lands in absent (distinct outcomes)
    fsm.fire("instance", "x", "stop")
    fsm.fire("instance", "x", "stopped_ok")
    assert _leaves(fsm, "instance") == ["provisioned", "stopped"]

    fsm.fire("instance", "x", "destroy")
    fsm.fire("instance", "x", "destroyed_ok")
    assert _leaves(fsm, "instance") == ["absent", "provisioned"]
    assert fsm.context("instance", "x")["desired"] == "running"


def test_instance_op_failure_goes_to_error() -> None:
    fsm = _fsm("instance")
    fsm.fire("instance", "x", "create")
    fsm.fire("instance", "x", "op_fail")
    assert _leaves(fsm, "instance") == ["error", "unprovisioned"]
    fsm.fire("instance", "x", "create")           # recover
    fsm.fire("instance", "x", "created_ok")
    assert _leaves(fsm, "instance") == ["running", "unprovisioned"]
