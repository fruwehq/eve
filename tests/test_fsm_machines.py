"""The core instance and package machines (core/fsm/*.yaml) over the Determa State engine.

Loading each bundle runs it through the engine's load-time validation; the tests then
exercise the key lifecycle transitions that replace state.py's PROVIDER_STATES /
PROVISION_STATES / PACKAGE_STATES.
"""

from __future__ import annotations

from pathlib import Path

from eve_sdk.fsm import EveFsm

CORE = Path(__file__).resolve().parents[1] / "core" / "fsm"


def _fsm(scope: str, machine_id: str | None = None, external: dict[str, str] | None = None) -> EveFsm:
    ext = dict(external or {})
    fsm = EveFsm(lambda s, k, names: {n: ext.get(n, "") for n in names})
    fsm.load(scope, (CORE / f"{scope}.yaml").read_text(), machine_id=machine_id)
    return fsm


def test_package_lifecycle() -> None:
    fsm = _fsm("package")
    assert fsm.leaves("package", "x") == ["unknown"]

    fsm.fire("package", "x", "absent")
    assert fsm.leaves("package", "x") == ["missing"]

    fsm.fire("package", "x", "install")
    assert fsm.leaves("package", "x") == ["installing"]

    fsm.fire("package", "x", "install_fail")
    assert fsm.leaves("package", "x") == ["failed"]

    fsm.fire("package", "x", "install")           # retry
    fsm.fire("package", "x", "install_ok")
    assert fsm.leaves("package", "x") == ["installed"]

    fsm.fire("package", "x", "absent")            # drift: disappeared out of band
    assert fsm.leaves("package", "x") == ["missing"]


def test_instance_provider_lifecycle() -> None:
    fsm = _fsm("instance", machine_id="instance_provider", external={"desired": "running"})
    assert fsm.leaves("instance", "x") == ["unknown"]

    fsm.fire("instance", "x", "create")
    fsm.fire("instance", "x", "created_ok")
    assert fsm.leaves("instance", "x") == ["running"]

    # stop lands in stopped; destroy lands in absent (distinct outcomes)
    fsm.fire("instance", "x", "stop")
    fsm.fire("instance", "x", "stopped_ok")
    assert fsm.leaves("instance", "x") == ["stopped"]

    fsm.fire("instance", "x", "destroy")
    fsm.fire("instance", "x", "destroyed_ok")
    assert fsm.leaves("instance", "x") == ["absent"]
    assert fsm.context("instance", "x")["desired"] == "running"

    # operator intent is authoritative: start recovers even from absent
    fsm.fire("instance", "x", "start")
    fsm.fire("instance", "x", "started_ok")
    assert fsm.leaves("instance", "x") == ["running"]


def test_instance_provision_lifecycle() -> None:
    fsm = _fsm("instance", machine_id="instance_provision")
    assert fsm.leaves("instance", "x") == ["unprovisioned"]

    fsm.fire("instance", "x", "provision")
    fsm.fire("instance", "x", "provision_ok")
    assert fsm.leaves("instance", "x") == ["provisioned"]

    fsm.fire("instance", "x", "provision")        # re-converge
    fsm.fire("instance", "x", "provision_fail")
    assert fsm.leaves("instance", "x") == ["provision_error"]

    fsm.fire("instance", "x", "provision")        # retry
    fsm.fire("instance", "x", "provision_ok")
    assert fsm.leaves("instance", "x") == ["provisioned"]


def test_instance_op_failure_goes_to_error() -> None:
    fsm = _fsm("instance", machine_id="instance_provider")
    fsm.fire("instance", "x", "create")
    fsm.fire("instance", "x", "op_fail")
    assert fsm.leaves("instance", "x") == ["error"]
    fsm.fire("instance", "x", "create")           # recover
    fsm.fire("instance", "x", "created_ok")
    assert fsm.leaves("instance", "x") == ["running"]
